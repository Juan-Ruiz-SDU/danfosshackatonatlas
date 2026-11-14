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
    words = raw.split()
    if len(words) > max_words:  # same length budget for everyone
        raw = " ".join(words[:max_words]) + " ..."
    style = meta.get("style") or re.sub(r"_\d+$", "", path.stem)
    return Doc(path, meta.get("brand", default_brand), style, raw.strip())


def load_docs(folder, default_brand, max_words):
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        return []
    return [read_doc(p, default_brand, max_words)
            for p in sorted(folder.iterdir())
            if p.suffix in {".md", ".txt"} and p.name.lower() != "readme.md"]


# --- filter 1: BM25 ----------------------------------------------------------
def tokens(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


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
                detail = e.read().decode(errors="replace")[:400]
                if e.code == 429 or e.code >= 500:
                    if "PerDay" in detail or "per day" in detail.lower():
                        sys.exit("Daily free quota used up. Run again tomorrow: cached "
                                 "answers are kept, so the run continues where it stopped.")
                    print(f"    limit/server error {e.code}, retrying in {wait}s ...", flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                sys.exit(f"API error {e.code}: {detail}")
            except urllib.error.URLError as e:
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
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--provider", choices=PROVIDERS, default="fake")
    ap.add_argument("--model", help="default depends on provider")
    ap.add_argument("--host", help="Ollama address, e.g. http://localhost:11434")
    ap.add_argument("--variants", nargs="+",
                    default=[str(REPO / "variants ManuJuan"), str(HERE / "corpus" / "danfoss_original")],
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
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--sleep", type=float,
                    help="seconds between API calls (default 6 for gemini, 0 otherwise)")
    ap.add_argument("--limit-questions", type=int, help="use only the first N questions")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()

    load_dotenv()
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
    print(f"Questions: {len(questions)}, repeats: {args.repeats}, top-k: {args.top_k}")
    print(f"Model: {args.provider}/{llm.model}  ->  {total} answers (cached ones are free)\n")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = pathlib.Path(args.out) / f"{stamp}_{args.provider}"
    out.mkdir(parents=True, exist_ok=True)
    raw = (out / "trials.jsonl").open("w", encoding="utf-8")

    rows, done = [], 0
    for target in targets:
        corpus = competitors + [target]  # one Danfoss page at a time vs. the same rivals
        bm25 = BM25(corpus)
        for qi, question in enumerate(questions):
            ranked = bm25.rank(question)
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
                results = "\n\n".join(f"[{i}] Source: {d.brand}\n{d.text}" for i, d in id_to_doc.items())
                text = llm.ask(SYSTEM, USER.format(question=question, results=results),
                               args.temperature, seed)
                cites, rec = parse_answer(text, id_to_doc)
                cited_brands = [id_to_doc[c].brand for c in cites]
                t_cites = sum(b.lower() == TARGET.lower() for b in cited_brands)
                in_context = target in shown
                row = {
                    "page": target.name, "style": target.style, "question": question,
                    "repeat": rep, "bm25_rank": rank, "retrieved": retrieved,
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
