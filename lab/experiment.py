#!/usr/bin/env python3
"""
Citation lab: does a rewritten Danfoss page get cited more by an AI answer
engine than the original page, when it competes with real competitor pages?

For every Danfoss page (each variant from Manu/Juan + the original pages) and
every buyer question, the lab simulates Google's two filters:

  1. Retrieval (like the blue links): BM25 ranks the Danfoss page against all
     competitor pages and keeps the top K.
  2. AI answer (like an AI Overview): an LLM answers the question using ONLY
     those K results and cites them as [D1], [D2]... The order of the results
     and their IDs are shuffled on every repeat, so position does not decide.

Then it counts, per writing style (plain, stats, sources, original...):
  retrieved   how often the Danfoss page made the top K
  cited       how often the answer cited the Danfoss page at least once
  share       Danfoss citations / all citations in the answer
  first       how often Danfoss was the first source cited
  recommended how often the answer named Danfoss as its recommendation

Usage (from the repo folder):
  python lab/experiment.py --provider fake               test the pipeline, no API, no cost
  python lab/experiment.py --provider gemini             real run with your Gemini key
  python lab/experiment.py --provider ollama --model qwen3:8b    private, local
  python lab/experiment.py --help                        all options

The Gemini key is read from the GEMINI_API_KEY environment variable or from a
.env file in the repo folder (already in .gitignore). Never commit the key.

Answers are cached in lab/cache/, so re-running the same experiment costs no
quota. Results go to lab/results/<date_time>/.

Standard library only. The chart needs:  pip install matplotlib
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
import os
import pathlib
import random
import re
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TARGET = "Danfoss"

PROVIDERS = {
    # name: (base URL of the OpenAI-compatible API, env var with the key, default model)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/",
               "GEMINI_API_KEY", "gemini-2.5-flash"),
    "ollama": ("http://localhost:11434/v1/", None, "qwen3:8b"),
    "openrouter": ("https://openrouter.ai/api/v1/", "OPENROUTER_API_KEY",
                   "openai/gpt-oss-20b:free"),
    "fake": (None, None, "fake"),
}

SYSTEM = """You are the AI answer box of a web search engine (like Google's AI Overview).
A buyer typed a question. You get the top search results, each with an ID like [D1].
Rules:
- Answer in about 120 words, using ONLY information from the search results.
- After every claim, cite the result(s) it comes from with their ID in square brackets, e.g. [D2].
- Only cite results you actually used.
- If the buyer asks for a recommendation, recommend the company/product the results best support.
- End with one last line exactly in this form:
RECOMMENDED: <company name, or "none">"""

USER = """Question: {question}

Search results:
{results}"""

CITE_RE = re.compile(r"\[\s*(D\d+(?:\s*,\s*D\d+)*)\s*\]")
REC_RE = re.compile(r"RECOMMENDED:\s*(.+)", re.IGNORECASE)
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOP = set("""a an and are as at be by can do does for from has have how i if in
into is it its my of on or our should so than that the their them then there
these they this to us was we what when where which who why will with you your
me best""".split())


# --- documents ---------------------------------------------------------------
class Doc:
    def __init__(self, path, brand, style, text):
        self.path, self.brand, self.style, self.text = path, brand, style, text
        self.name = path.stem


def read_doc(path, default_brand, max_words):
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta = {}
    m = FRONT_RE.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    full = raw.strip()
    words = raw.split()
    if len(words) > max_words:  # same length budget for everyone
        raw = " ".join(words[:max_words]) + " ..."
    style = meta.get("style") or re.sub(r"_\d+$", "", path.stem)
    doc = Doc(path, meta.get("brand", default_brand), style, raw.strip())
    doc.full_text = full  # whole page with its line breaks, for passage ranking
    return doc


def load_docs(folder, default_brand, max_words):
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        return []
    return [read_doc(p, default_brand, max_words)
            for p in sorted(folder.iterdir())
            if p.suffix in {".md", ".txt"} and p.name.lower() != "readme.md"]


# --- filter 1: BM25 ----------------------------------------------------------
# Words ending in -s that are not plurals (or whose plural rule would mangle them).
NOT_PLURAL = {"series", "species", "gas", "bus", "lens", "chassis", "always", "perhaps"}


def stem(word):
    """Light English plural stemmer: pumps -> pump, boxes -> box, batteries -> battery.
    Only plural endings, nothing aggressive. Hyphenated words are stemmed per part."""
    if "-" in word:
        return "-".join(stem(p) for p in word.split("-"))
    if len(word) <= 3 or word in NOT_PLURAL or word.isdigit():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"                      # batteries -> battery
    if word.endswith(("sses", "ches", "shes", "xes")):
        return word[:-2]                            # classes, switches, meshes, boxes
    if word.endswith(("ss", "us", "is")):
        return word                                 # class, status, analysis
    if word.endswith("s"):
        return word[:-1]                            # pumps, exchangers, sizes
    return word


def tokens(text):
    return [stem(t) for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.tf = [collections.Counter(tokens(d.text)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / len(self.len)
        df = collections.Counter(t for c in self.tf for t in c)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def rank(self, query):
        q = tokens(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                f = self.tf[i].get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        return scored


# --- filter 1, passage version -------------------------------------------------
# AI search engines rank passages, not whole pages: Google's AI Overviews pick
# passages for each sub-question, Bing grounds answers on chunks, Perplexity
# splits pages into sub-document spans. With --retrieval passage, every page is
# cut into passages at its headings; a page ranks by its best passage, and the
# AI sees that page's best passages instead of its first N words. A clear
# heading then matters, because each passage carries its heading path.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def split_passages(text, max_words=200):
    """[{'heading': 'H1 > H2', 'text': body}] for a Markdown/plain text page.
    Sections are split at headings; a long section is cut at paragraph (line)
    boundaries into pieces of about max_words."""
    path, buf, out = [], [], []

    def flush():
        crumb = " > ".join(t for _, t in path)
        piece, n = [], 0
        for para in buf:
            w = len(para.split())
            if piece and n + w > max_words:
                out.append({"heading": crumb, "text": "\n".join(piece)})
                piece, n = [], 0
            while w > max_words:  # one huge paragraph: cut by words
                words = para.split()
                out.append({"heading": crumb, "text": " ".join(words[:max_words])})
                para = " ".join(words[max_words:])
                w = len(para.split())
            if w:
                piece.append(para)
                n += w
        if piece:
            if out and n < 40 and out[-1]["heading"] == crumb:  # tiny tail: join the previous piece
                out[-1]["text"] += "\n" + "\n".join(piece)
            else:
                out.append({"heading": crumb, "text": "\n".join(piece)})
        buf.clear()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path = [(l, t) for l, t in path if l < level] + [(level, m.group(2))]
        else:
            buf.append(line)
    flush()
    if not out and path:  # a page that is only headings
        out.append({"heading": " > ".join(t for _, t in path), "text": ""})
    return out


class Passage:
    def __init__(self, doc, index, heading, body):
        self.doc, self.index, self.heading, self.body = doc, index, heading, body
        self.text = (heading + "\n" + body).strip()  # the heading path counts for ranking


class PassageRanker:
    """BM25 over the passages of all pages. rank() orders pages by their best
    passage; context() gives the text the AI sees for one page."""

    def __init__(self, docs, max_words=200):
        self.docs = docs
        self.items = []
        for d in docs:
            src = getattr(d, "full_text", None) or d.text
            for i, p in enumerate(split_passages(src, max_words)):
                self.items.append(Passage(d, i, p["heading"], p["text"]))
        self.bm25 = BM25(self.items) if self.items else None
        self._query, self._scores = None, []

    def scores(self, query):
        """[(score, passage)], best first (cached for the last query)."""
        if query != self._query:
            self._query = query
            self._scores = self.bm25.rank(query) if self.bm25 else []
        return self._scores

    def rank(self, query):
        best = {}
        for s, p in self.scores(query):
            if id(p.doc) not in best:
                best[id(p.doc)] = (s, p.doc)
        ranked = sorted(best.values(), key=lambda x: -x[0])
        seen = {id(d) for _, d in ranked}
        return ranked + [(0.0, d) for d in self.docs if id(d) not in seen]

    def best(self, doc, query, n=3):
        """The page's n best passages for the query, in page order."""
        mine = [(s, p) for s, p in self.scores(query) if p.doc is doc][:n]
        return [(s, p) for s, p in sorted(mine, key=lambda x: x[1].index)]

    def context(self, doc, query, n=3, max_words=700):
        text = "\n\n".join(p.text for _, p in self.best(doc, query, n))
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + " ..."
        return text


# --- filter 1, words + meaning (hybrid) ----------------------------------------
# BM25 only matches words: a page that says "BPHE for residential heating" scores
# low for "heat exchanger for a heat pump" although it answers it. AI search
# engines combine keyword ranking with meaning (embedding) ranking. With
# --retrieval hybrid, BM25 and embedding similarity each rank the whole pages,
# and the two rankings are merged with reciprocal rank fusion (RRF), the usual
# way to combine them. The AI sees the same text as with --retrieval page, so a
# comparison of the two isolates the ranking. Embeddings come from an Ollama
# server (ollama pull nomic-embed-text) and are cached on disk per text.
EMBED_MODEL = "nomic-embed-text"
RRF_K = 60  # the standard RRF constant: score = sum of 1 / (60 + rank)


class Embedder:
    def __init__(self, host="http://localhost:11434", model=EMBED_MODEL, cache_dir=None):
        host = (host or "http://localhost:11434").rstrip("/")
        self.host = host[:-3] if host.endswith("/v1") else host
        self.model = model or EMBED_MODEL
        self.cache_dir = pathlib.Path(cache_dir) / "embeddings" if cache_dir else None
        self.mem = {}

    def _key(self, text):
        return hashlib.sha256(f"{self.model}\n{text}".encode("utf-8")).hexdigest()

    def embed(self, texts):
        """One vector per text, in order. Cached in memory and on disk."""
        todo = []
        for t in dict.fromkeys(texts):
            k = self._key(t)
            if k in self.mem:
                continue
            f = self.cache_dir / f"{k}.json" if self.cache_dir else None
            if f and f.is_file():
                self.mem[k] = json.loads(f.read_text(encoding="utf-8"))
            else:
                todo.append(t)
        for i in range(0, len(todo), 16):
            batch = todo[i:i + 16]
            for t, v in zip(batch, self._call(batch)):
                k = self._key(t)
                self.mem[k] = v
                if self.cache_dir:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    (self.cache_dir / f"{k}.json").write_text(json.dumps(v), encoding="utf-8")
        return [self.mem[self._key(t)] for t in texts]

    def _call(self, batch):
        body = json.dumps({"model": self.model, "input": batch, "truncate": True}).encode("utf-8")
        req = urllib.request.Request(self.host + "/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                vecs = json.loads(resp.read())["embeddings"]
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404 or "not found" in msg.lower():
                raise RuntimeError(
                    f"The embedding model '{self.model}' is not installed on the Ollama server at "
                    f"{self.host}. On that computer run:  ollama pull {self.model}") from None
            raise RuntimeError(f"Ollama at {self.host} refused the embedding request "
                               f"({e.code}): {msg}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Cannot reach Ollama at {self.host} for embeddings "
                               f"({getattr(e, 'reason', e)}). Words + meaning ranking needs "
                               "Ollama with the nomic-embed-text model.") from None
        if len(vecs) != len(batch):
            raise RuntimeError(f"Ollama at {self.host} returned {len(vecs)} embeddings "
                               f"for {len(batch)} texts.")
        return vecs


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class HybridRanker:
    """Words + meaning: BM25 and embedding similarity each rank the pages, merged
    with reciprocal rank fusion. Same interface as BM25: rank(query) -> [(score, doc)]."""

    def __init__(self, docs, embedder):
        self.docs = docs
        self.bm25 = BM25(docs)
        self.embedder = embedder
        # nomic-embed-text expects these task prefixes
        self.vecs = embedder.embed(["search_document: " + d.text for d in docs])

    def meaning(self, query):
        """[(similarity, doc)], most similar first."""
        q = self.embedder.embed(["search_query: " + query])[0]
        sims = [(cosine(q, v), d) for v, d in zip(self.vecs, self.docs)]
        return sorted(sims, key=lambda x: -x[0])

    def rank(self, query):
        score = collections.defaultdict(float)
        for ranking in (self.bm25.rank(query), self.meaning(query)):
            for r, (_, d) in enumerate(ranking, 1):
                score[id(d)] += 1 / (RRF_K + r)
        return sorted(((score[id(d)], d) for d in self.docs), key=lambda x: -x[0])


# --- filter 2: the LLM answer ------------------------------------------------
def load_dotenv():
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class LLM:
    def __init__(self, provider, model, host, sleep, cache_dir):
        base, key_var, default_model = PROVIDERS[provider]
        self.provider, self.model = provider, model or default_model
        self.base = (host.rstrip("/") + "/v1/") if (host and provider == "ollama") else base
        self.key = os.environ.get(key_var) if key_var else None
        if key_var and not self.key:
            sys.exit(f"No API key. Put {key_var}=your_key in a .env file in the repo "
                     f"folder, or set the {key_var} environment variable.")
        self.sleep = sleep
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = self.hits = 0

    def ask(self, system, user, temperature, seed):
        key = hashlib.sha256(json.dumps(
            [self.provider, self.model, system, user, temperature, seed]).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            self.hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["text"]
        text = self._fake(user, seed) if self.provider == "fake" else self._call(system, user, temperature)
        path.write_text(json.dumps({"model": self.model, "text": text}), encoding="utf-8")
        self.calls += 1
        return text

    def _fake(self, user, seed):
        """Offline stand-in: cites 1-3 random results. Only tests the plumbing."""
        rng = random.Random(seed + len(user))
        ids = re.findall(r"^\[(D\d+)\]", user, re.MULTILINE)
        cited = rng.sample(ids, k=min(len(ids), rng.randint(1, 3)))
        brands = dict(re.findall(r"^\[(D\d+)\] Source: (.+)$", user, re.MULTILINE))
        return " ".join(f"Claim [{d}]." for d in cited) + f"\nRECOMMENDED: {brands.get(cited[0], 'none')}"

    def _call(self, system, user, temperature):
        body = json.dumps({
            "model": self.model, "temperature": temperature,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        wait = int(os.environ.get("LAB_RETRY_WAIT", 10))
        for attempt in range(6):
            if self.sleep:
                time.sleep(self.sleep)  # stay under the free per-minute limit
            req = urllib.request.Request(self.base + "chat/completions", data=body, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"] or ""
                return THINK_RE.sub("", text).strip()
            except urllib.error.HTTPError as e:
                full = e.read().decode(errors="replace")
                detail = full[:400]
                if e.code == 429 or e.code >= 500:
                    if "PerDay" in full or "per day" in full.lower():
                        sys.exit("Daily free quota used up. Run again tomorrow: cached "
                                 "answers are kept, so the run continues where it stopped.")
                    print(f"    limit/server error {e.code}, retrying in {wait}s ...", flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                sys.exit(f"API error {e.code}: {detail}")
            except (urllib.error.URLError, TimeoutError) as e:
                if self.provider == "ollama":
                    sys.exit(f"Cannot reach Ollama ({e}). Start the Ollama app first.")
                print(f"    network error ({e}), retrying in {wait}s ...", flush=True)
                time.sleep(wait)
        sys.exit("Gave up after 6 attempts. Check your connection or quota.")


def parse_answer(text, id_to_doc):
    cites = []
    for group in CITE_RE.findall(text):
        cites += [c.strip() for c in group.split(",")]
    cites = [c for c in cites if c in id_to_doc]
    m = REC_RE.search(text)
    rec = m.group(1).strip().strip("*.") if m else ""
    return cites, rec


# --- statistics --------------------------------------------------------------
def wilson(k, n, z=1.96):
    """95% confidence interval for a rate k/n. Wide interval = not enough data."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(x):
    return f"{100 * x:.0f}%"


# --- main --------------------------------------------------------------------
def refresh_site_copies():
    """The 'restructured' page is the team's website copy from the Atlas app, which
    takes product facts from the wiki. Rebuild it first, so the lab tests it with
    the wiki as it is now. Quietly skipped if the app or the copy is missing."""
    try:
        sys.path.insert(0, str(REPO / "app"))
        import products as atlas_products
        import website
        for p in atlas_products.list_products():
            prod = atlas_products.get(p["slug"])
            if prod.get("restructured_dir"):
                url = next((u for b, u in atlas_products.source_list(prod) if b.lower() == TARGET.lower()), "")
                if website.refresh(prod, url):
                    print(f"Website copy of '{p['slug']}' rebuilt from the current wiki")
    except Exception as e:  # noqa: BLE001
        print(f"(website copy not rebuilt: {e})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--provider", choices=PROVIDERS, default="fake")
    ap.add_argument("--model", help="default depends on provider")
    ap.add_argument("--host", help="Ollama address, e.g. http://localhost:11434")
    ap.add_argument("--variants", nargs="+",
                    default=[str(REPO / "variants ManuJuan"), str(HERE / "corpus" / "danfoss_original"),
                             str(HERE / "corpus" / "danfoss_restructured")],
                    help="folders with Danfoss pages; style = file name before _N")
    ap.add_argument("--competitors", default=str(HERE / "corpus" / "competitors"))
    ap.add_argument("--questions", default=str(HERE / "questions.txt"))
    ap.add_argument("--styles", help="only these styles, comma list (e.g. plain,stats)")
    ap.add_argument("--top-k", type=int, default=5, help="results the AI sees")
    ap.add_argument("--repeats", type=int, default=2, help="shuffled repeats per question")
    ap.add_argument("--max-words", type=int, default=700,
                    help="cut every page to this many words, so long pages do not win by length")
    ap.add_argument("--force-target", action="store_true",
                    help="always put the Danfoss page in the AI's results, even if BM25 "
                         "ranked it lower: tests the writing alone, without the retrieval filter")
    ap.add_argument("--retrieval", choices=["page", "passage", "hybrid"], default="page",
                    help="page: BM25 over whole pages, the AI sees each page's first --max-words "
                         "words (the original lab). passage: BM25 over passages cut at headings, "
                         "a page ranks by its best passage and the AI sees its best passages. "
                         "hybrid: words + meaning, BM25 and embedding similarity (Ollama, "
                         "--embed-model) rank whole pages, merged by reciprocal rank fusion; "
                         "the AI sees the same text as with page. "
                         "Results of the different rankings are not comparable")
    ap.add_argument("--embed-model", default=EMBED_MODEL,
                    help="Ollama embedding model for --retrieval hybrid (uses --host, "
                         "default http://localhost:11434)")
    ap.add_argument("--passage-words", type=int, default=200,
                    help="passage length for --retrieval passage")
    ap.add_argument("--passages", type=int, default=3,
                    help="best passages per page the AI sees with --retrieval passage")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--sleep", type=float,
                    help="seconds between API calls (default 6 for gemini, 0 otherwise)")
    ap.add_argument("--limit-questions", type=int, help="use only the first N questions")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()

    load_dotenv()
    refresh_site_copies()
    max_words = args.max_words
    targets = [d for folder in args.variants for d in load_docs(folder, TARGET, max_words)]
    targets = [d for d in targets if d.brand.lower() == TARGET.lower()]
    if args.styles:
        keep = {s.strip() for s in args.styles.split(",")}
        targets = [d for d in targets if d.style in keep]
    competitors = [d for d in load_docs(args.competitors, "unknown", max_words)
                   if d.brand.lower() != TARGET.lower()]
    questions = [q.strip() for q in pathlib.Path(args.questions).read_text(encoding="utf-8").splitlines()
                 if q.strip() and not q.lstrip().startswith("#")][:args.limit_questions]

    if not targets:
        sys.exit("No Danfoss pages found. Check --variants.")
    if len(competitors) < 2:
        sys.exit(f"Only {len(competitors)} competitor pages in {args.competitors}.\n"
                 "Run  python lab/fetch_sources.py  first (or add pages by hand).")

    if len(competitors) + 1 <= args.top_k:
        print(f"WARNING: only {len(competitors) + 1} pages per test and top-k is {args.top_k}: "
              "every page is always retrieved, so 'Retrieved' means nothing. "
              "Add competitor pages or lower --top-k.\n")
    sleep = args.sleep if args.sleep is not None else (6.0 if args.provider == "gemini" else 0.0)
    llm = LLM(args.provider, args.model, args.host, sleep, HERE / "cache")
    styles = sorted({d.style for d in targets})
    total = len(targets) * len(questions) * args.repeats
    print(f"Danfoss pages: {len(targets)} ({', '.join(f'{s}: {sum(d.style == s for d in targets)}' for s in styles)})")
    print(f"Competitor pages: {len(competitors)} ({', '.join(sorted({d.brand for d in competitors}))})")
    print(f"Questions: {len(questions)}, repeats: {args.repeats}, top-k: {args.top_k}, "
          f"ranking: {args.retrieval}")
    print(f"Model: {args.provider}/{llm.model}  ->  {total} answers (cached ones are free)\n")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = pathlib.Path(args.out) / f"{stamp}_{args.provider}"
    out.mkdir(parents=True, exist_ok=True)
    raw = (out / "trials.jsonl").open("w", encoding="utf-8")

    embedder = (Embedder(args.host, args.embed_model, HERE / "cache")
                if args.retrieval == "hybrid" else None)
    rows, done = [], 0
    for target in targets:
        corpus = competitors + [target]  # one Danfoss page at a time vs. the same rivals
        if args.retrieval == "hybrid":
            try:
                ranker = HybridRanker(corpus, embedder)
            except RuntimeError as e:
                sys.exit(str(e))

            def shown_text(d, q):
                return d.text
        elif args.retrieval == "passage":
            ranker = PassageRanker(corpus, args.passage_words)

            def shown_text(d, q):
                return ranker.context(d, q, args.passages, max_words)
        else:
            ranker = BM25(corpus)

            def shown_text(d, q):
                return d.text
        for qi, question in enumerate(questions):
            ranked = ranker.rank(question)
            rank = next(i for i, (_, d) in enumerate(ranked) if d is target) + 1
            top = [d for _, d in ranked[:args.top_k]]
            retrieved = target in top
            if args.force_target and not retrieved:
                top = top[:-1] + [target]
            for rep in range(args.repeats):
                seed = args.seed + 1000 * rep + qi
                shown = top[:]
                random.Random(seed).shuffle(shown)
                id_to_doc = {f"D{i + 1}": d for i, d in enumerate(shown)}
                results = "\n\n".join(f"[{i}] Source: {d.brand}\n{shown_text(d, question)}"
                                      for i, d in id_to_doc.items())
                text = llm.ask(SYSTEM, USER.format(question=question, results=results),
                               args.temperature, seed)
                cites, rec = parse_answer(text, id_to_doc)
                cited_brands = [id_to_doc[c].brand for c in cites]
                t_cites = sum(b.lower() == TARGET.lower() for b in cited_brands)
                in_context = target in shown
                row = {
                    "page": target.name, "style": target.style, "question": question,
                    "repeat": rep, "bm25_rank": rank, "retrieved": retrieved,
                    "retrieval": args.retrieval,
                    "in_context": in_context,
                    "cited": t_cites > 0,
                    "share": t_cites / len(cites) if cites else 0.0,
                    "first": bool(cited_brands) and cited_brands[0].lower() == TARGET.lower(),
                    "recommended": TARGET.lower() in rec.lower(),
                    "n_citations": len(cites), "cited_brands": cited_brands,
                    "recommendation": rec,
                    "context": {i: f"{d.brand} ({d.name})" for i, d in id_to_doc.items()},
                    "answer": text,
                }
                rows.append(row)
                raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                raw.flush()
                done += 1
                mark = "CITED" if row["cited"] else ("not cited" if in_context else "not retrieved")
                print(f"[{done}/{total}] {target.name:<12} q{qi + 1:<2} r{rep}  "
                      f"bm25 #{rank:<2} {mark:<13} -> {', '.join(cited_brands) or 'no citations'}",
                      flush=True)
    raw.close()

    # --- summary per style ---
    summary = []
    for style in styles:
        rs = [r for r in rows if r["style"] == style]
        n = len(rs)
        ctx = [r for r in rs if r["in_context"]]
        k = sum(r["cited"] for r in rs)
        lo, hi = wilson(k, n)
        summary.append({
            "style": style, "pages": len({r["page"] for r in rs}), "trials": n,
            "retrieved": sum(r["retrieved"] for r in rs) / n,
            "mean_bm25_rank": sum(r["bm25_rank"] for r in rs) / n,
            "cited": k / n, "cited_ci_low": lo, "cited_ci_high": hi,
            "cited_when_shown": (sum(r["cited"] for r in ctx) / len(ctx)) if ctx else 0.0,
            "share": sum(r["share"] for r in rs) / n,
            "first": sum(r["first"] for r in rs) / n,
            "recommended": sum(r["recommended"] for r in rs) / n,
        })
    summary.sort(key=lambda s: -s["share"])

    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    brand_cites = collections.Counter(b for r in rows for b in r["cited_brands"])
    all_cites = sum(brand_cites.values()) or 1

    lines = [
        f"# Citation lab results ({stamp})", "",
        f"Model: `{args.provider}/{llm.model}` · {len(questions)} questions × {args.repeats} repeats · "
        f"top-{args.top_k} results · pages cut to {max_words} words"
        + (f" · ranking: passages (best {args.passages} per page, ~{args.passage_words} words each)"
           if args.retrieval == "passage" else "")
        + (f" · ranking: words + meaning (BM25 + `{args.embed_model}` embeddings, merged by RRF)"
           if args.retrieval == "hybrid" else "")
        + (" · Danfoss page forced into the results" if args.force_target else ""), "",
        f"Competitors: {', '.join(f'{b} ({sum(d.brand == b for d in competitors)} pages)' for b in sorted({d.brand for d in competitors}))}", "",
        "## Danfoss, by writing style (best first)", "",
        "| Style | Pages | Trials | Retrieved (top-k) | Cited | 95% range of Cited | Cited when shown | Citation share | Cited first | Recommended |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(f"| {s['style']} | {s['pages']} | {s['trials']} | {pct(s['retrieved'])} | "
                     f"{pct(s['cited'])} | {pct(s['cited_ci_low'])}–{pct(s['cited_ci_high'])} | "
                     f"{pct(s['cited_when_shown'])} | {pct(s['share'])} | {pct(s['first'])} | "
                     f"{pct(s['recommended'])} |")
    lines += [
        "", "## All citations, by brand", "",
        "| Brand | Citations | Share |", "|---|---|---|",
        *[f"| {b} | {c} | {pct(c / all_cites)} |" for b, c in brand_cites.most_common()],
        "", "## How to read this", "",
        "- **Retrieved**: the page made BM25's top-k (Google's blue links). If this is low, the AI never even sees the page.",
        "- **Cited when shown**: of the times the AI saw the page, how often it cited it. This isolates the writing quality.",
        "- **Citation share**: Danfoss citations / all citations in the answer, averaged. The headline metric.",
        "- **95% range**: if two styles' ranges overlap a lot, the difference may be luck. Add questions or repeats before claiming a winner.",
        "",
    ]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        names = [s["style"] for s in summary]
        vals = [100 * s["share"] for s in summary]
        fig, ax = plt.subplots(figsize=(7, 0.6 * len(names) + 1.5))
        ax.barh(names[::-1], vals[::-1], color="#2a6fdb")
        for i, v in enumerate(vals[::-1]):
            ax.text(v + 1, i, f"{v:.0f}%", va="center")
        ax.set_xlim(0, 100)
        ax.set_xlabel("Danfoss citation share in the AI answer (%)")
        ax.set_title("Which way of writing gets Danfoss cited?")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(out / "chart.png", dpi=150)
    except ImportError:
        pass

    print("\n" + "\n".join(lines[6:10 + len(summary)]))
    print(f"\nAPI calls: {llm.calls}, from cache: {llm.hits}")
    print(f"Saved in {out}  (summary.md, summary.csv, trials.jsonl"
          + (", chart.png)" if (out / "chart.png").exists() else ")"))
    if args.provider == "fake":
        print("\nNOTE: --provider fake cites at random. These numbers only prove the "
              "pipeline works; they say nothing about the pages.")


if __name__ == "__main__":
    main()
