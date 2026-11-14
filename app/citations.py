"""
The "Citations" tab: which pages Gemini (with Google Search) cites for the buyer
prompts, how that changes from one update to the next, and how our latest pages
compare with the pages it cites.

The agent is lab/discover_sources.py: it asks Gemini every prompt in
prompts/prompts.txt with Google Search switched on, records the searches Gemini
ran (its sub-queries) and the pages it cited, and imports those pages as text.
Runs are kept in lab/discovered/runs/<date>.jsonl, so the history is visible.

What "value" Gemini gives each document
  Gemini does not rank pages with BM25 and gives no score per page. It does say
  which pieces of its answer each page supports. A page's SHARE is the part of
  the answer it supports (see discover_sources.parse_grounding). That is the
  number shown per document: real, observed, but only one engine on one day.

Comparing with our pages (no wiki involved)
  Only two things are compared: the text of the cited pages, and our latest
  generated pages (the website copy, the last Atlas run, the newest variants).
  - BM25 per sub-query: does our page have a passage that ranks with the cited ones?
  - The passage of each cited page that best matches what Gemini took from it.
  - On request, an AI reviewer scores the passages on a rubric of checkable
    signals and explains why the cited pages won. To keep it from rewarding
    markdown or length, every passage is plain text, cut to the same length,
    with brand names hidden and the order shuffled. Its scores are compared with
    Gemini's real shares, so we can see whether the reviewer agrees with the engine.
"""
import collections
import contextlib
import hashlib
import json
import pathlib
import random
import re
import sys

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO / "lab"))
import discover_sources as disc  # noqa: E402
import experiment as lab  # noqa: E402

import ai  # noqa: E402

OUT = disc.OUT
RUNS = OUT / "runs"
CORPUS = disc.CORPUS
EXPLAIN_CACHE = OUT / "explanations"
PROMPTS = REPO / "prompts" / "prompts.txt"


# --- prompts and runs -------------------------------------------------------------
def prompt_sections():
    """{section title: [prompts]} from prompts/prompts.txt ('# Title' lines start a section)."""
    out, cur = collections.OrderedDict(), "All prompts"
    for line in PROMPTS.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            if title and not title.lower().startswith(("one prompt", "lines starting")):
                cur = title
            continue
        if s:
            out.setdefault(cur, []).append(s)
    return out


def list_runs():
    if not RUNS.is_dir():
        return []
    return sorted(p for p in RUNS.glob("*.jsonl") if not p.name.endswith(".partial.jsonl"))


def load_run(name):
    path = RUNS / name
    if path.parent != RUNS or not path.is_file():
        raise ValueError(f"No run '{name}'")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _share(s, row):
    """A source's share of the answer. Runs made before shares were recorded
    only have support counts: use those, split over all supports of the answer."""
    if s.get("share") is not None:
        return float(s["share"])
    total = sum(x.get("supports", 0) for x in row["sources"]) or 1
    return s.get("supports", 0) / total


def is_target(s):
    return disc.TARGET in (s.get("domain") or "")


def history():
    """One line per update: prompts, sources, how often Danfoss is cited and its
    share of the answers, the most cited sites; plus each top site's share per run."""
    runs, site_share = [], collections.defaultdict(dict)
    for path in list_runs():
        rows = load_run(path.name)
        if not rows:
            continue
        sites = collections.Counter()
        dshare, dcited, dfirst = 0.0, 0, 0
        for r in rows:
            for s in r["sources"]:
                sites[s.get("domain") or "?"] += _share(s, r)
            ds = sum(_share(s, r) for s in r["sources"] if is_target(s))
            dshare += ds
            dcited += ds > 0
            dfirst += any(is_target(s) for s in r["sources"] if s.get("rank") == 1)
        n = len(rows)
        runs.append({"run": path.name, "date": rows[0].get("asked_at", path.stem)[:16].replace("T", " "),
                     "model": rows[0].get("model", ""), "prompts": n,
                     "sources": len({s.get("url") for r in rows for s in r["sources"] if s.get("url")}),
                     "danfoss_answers": dcited, "danfoss_first": dfirst, "danfoss_share": round(dshare / n, 4),
                     "top_sites": [(d, round(v / n, 4)) for d, v in sites.most_common(6)],
                     "has_shares": any(s.get("share") is not None for r in rows for s in r["sources"])})
        for d, v in sites.items():
            site_share[d][path.name] = round(v / n, 4)
    top = sorted(site_share, key=lambda d: -sum(site_share[d].values()))[:10]
    return {"runs": runs[::-1], "sites": [{"site": d, "by_run": site_share[d]} for d in top]}


def lab_history(p):
    """The Run tab's citation tests over time (simulated engine): the best version's
    citation rate per run, with the product's targets."""
    out = []
    for f in sorted((p["folder"] / "runs").glob("*/result.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tg = r.get("targets") or {}
        out.append({"run": r.get("run", f.parent.name), "date": f.parent.name[:10] + " " + f.parent.name[11:13] + ":" + f.parent.name[13:15],
                    "style": r["winner"]["name"], "cited_pct": round(100 * r["winner"]["cited"], 1),
                    "share_pct": round(100 * r["winner"]["share"], 1),
                    "first_count": tg.get("first_count"), "trials": tg.get("trials"), "met": tg.get("met")})
    return out


def run_summary(name):
    rows = load_run(name)
    out = []
    for i, r in enumerate(rows):
        srcs = sorted(r["sources"], key=lambda s: -_share(s, r))
        out.append({"i": i, "prompt": r["prompt"], "sources": len(srcs),
                    "queries": len(r.get("search_queries", [])),
                    "danfoss_share": round(sum(_share(s, r) for s in srcs if is_target(s)), 4),
                    "top": (srcs[0].get("domain") if srcs else ""),
                    "top_share": round(_share(srcs[0], r), 4) if srcs else 0})
    return out


# --- our latest pages ----------------------------------------------------------------------
def our_pages(p, danfoss_url):
    """Our latest generated pages: the website copy of the product page, the
    variants of the last Atlas run, and the newest variant of each style."""
    out = []
    try:
        import website
        pid = website.lab_page(p, danfoss_url)
        if pid:
            import webpage
            _, items = website._copy_items(p, pid)
            out.append({"id": f"site:{pid}", "label": f"Website copy: {pid}", "text": webpage.to_markdown(items)})
    except Exception:  # noqa: BLE001  (no website copy yet)
        pass
    runs = sorted((p["folder"] / "runs").glob("*/variants")) if (p["folder"] / "runs").is_dir() else []
    if runs:
        for f in sorted(runs[-1].glob("*.md")):
            out.append({"id": f"run:{runs[-1].parent.name}:{f.stem}",
                        "label": f"Last Atlas run ({runs[-1].parent.name}): {f.stem}",
                        "text": f.read_text(encoding="utf-8")})
    vdir = REPO / "variants ManuJuan"
    if vdir.is_dir():
        newest = {}
        for f in vdir.glob("*.md"):
            m = re.fullmatch(r"(.+?)_(\d+)", f.stem)
            if m and (m.group(1) not in newest or int(m.group(2)) > newest[m.group(1)][0]):
                newest[m.group(1)] = (int(m.group(2)), f)
        for style, (_, f) in sorted(newest.items()):
            out.append({"id": f"variant:{f.stem}", "label": f"Newest variant: {f.stem}",
                        "text": f.read_text(encoding="utf-8")})
    return out


# --- comparing one answer with our page -------------------------------------------------
class _Doc:
    def __init__(self, name, brand, text):
        self.name, self.brand, self.style = name, brand, name
        self.full_text, self.text = text, " ".join(text.split()[:700])


def cited_docs(row):
    """The cited pages we imported, with Gemini's share of the answer for each."""
    docs = []
    for s in sorted(row["sources"], key=lambda s: s.get("rank") or 99):
        if not s.get("url"):
            continue
        f = disc.page_file(s["url"])
        if not f.is_file():
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        m = lab.FRONT_RE.match(raw)
        text = raw[m.end():] if m else raw
        docs.append({"source": s, "doc": _Doc(s.get("domain") or s["url"], disc.brand_of(s.get("domain", "")), text)})
    return docs


def compare(row, ours):
    """Per sub-query: where our page's best passage ranks among the cited pages'
    passages (BM25), and which page leads. Per cited page: Gemini's share and the
    passage that best matches what Gemini took from it."""
    cited = cited_docs(row)
    me = _Doc("ours", "Danfoss", ours["text"])
    corpus = [c["doc"] for c in cited] + [me]
    queries = [row["prompt"]] + [q for q in row.get("search_queries", []) if q != row["prompt"]]
    ranker = lab.PassageRanker(corpus) if cited else None
    per_query = []
    for q in queries:
        if not ranker:
            break
        ranked = ranker.rank(q)
        rank = next(i for i, (_, d) in enumerate(ranked) if d is me) + 1
        best = ranker.best(me, q, 1)
        lead = ranked[0][1]
        per_query.append({"query": q, "our_rank": rank, "of": len(corpus),
                          "leader": "our page" if lead is me else lead.name,
                          "our_passage": (best[0][1].heading + " — " + best[0][1].body[:220]) if best else "",
                          "answered": rank == 1})
    per_doc = []
    for c in cited:
        s = c["source"]
        used = []
        seg_text = " ".join(s.get("segments") or [])
        if seg_text:
            pr = lab.PassageRanker([c["doc"]])
            used = [p.body[:400] for _, p in pr.best(c["doc"], seg_text, 1)]
        per_doc.append({"site": s.get("domain"), "url": s.get("url"), "rank": s.get("rank"),
                        "share": _share(s, row), "supports": s.get("supports", 0),
                        "confidence": s.get("confidence"), "segments": s.get("segments") or [],
                        "likely_passage": used[0] if used else ""})
    not_imported = [{"site": s.get("domain"), "url": s.get("url"), "share": _share(s, row)}
                    for s in row["sources"] if s.get("url") and not disc.page_file(s["url"]).is_file()]
    return {"queries": per_query, "docs": per_doc, "not_imported": not_imported,
            "answered": sum(q["answered"] for q in per_query), "n_queries": len(per_query)}


# --- the AI reviewer: why did Gemini cite these pages? --------------------------------------
RUBRIC = [
    ("direct_answer", "The first sentence answers the question or the sub-query directly"),
    ("specific_figures", "Gives specific figures with units (capacity, pressure, temperature, efficiency)"),
    ("named_specifics", "Names concrete models, refrigerants, standards or applications"),
    ("definition_or_comparison", "Defines the thing asked about or compares options"),
    ("scope_match", "Is about exactly what the question asks (product type and application)"),
    ("self_contained", "Can be understood alone, without the rest of the page"),
]

REVIEW_SYSTEM = """You review short text passages for a study of AI search citations.
You get a buyer question, the searches an AI engine ran for it, and passages from
several web pages, labelled A, B, C... Brand names are hidden as [brand]. All passages
are plain text and cut to the same length ON PURPOSE: length and formatting must play
no role in your scores.

For EACH passage, score each criterion 0 (no), 1 (partly) or 2 (yes), judging only
what the text says:
{rubric}

Then explain, in at most 4 sentences, which passages best serve the question and why,
pointing at concrete content (a figure, a named model, a definition) - never at length,
tone or formatting. Then list what the weakest passages would need to add, as kinds of
facts (for example "the working pressure per model"), never as text to copy.

Reply with JSON only:
{{"scores": {{"A": {{"direct_answer": 0, "...": 0}}, "B": {{}}}},
  "why": "...", "missing_in_weakest": ["..."]}}"""


def _plain(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(#{1,6}|[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"[|*_`>#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


BRANDS = r"danfoss|alfa ?laval|swep|hexonic|kelvion|ciat|carrier|daikin|bitzer|dorin|sondex|micro plate|hexselector"


def _mask(text):
    return re.sub(BRANDS, "[brand]", text, flags=re.I)


def _excerpt(doc, queries, words):
    """The page's passages that best match the question and its searches, best
    first, until there are `words` words (in page order, as plain text)."""
    pr = lab.PassageRanker([doc])
    picked, n = [], 0
    for _, p in pr.scores(" ".join(queries)):
        if n >= words:
            break
        picked.append(p)
        n += len(p.body.split())
    text = _plain(" ".join(p.body for p in sorted(picked, key=lambda p: p.index)) or doc.full_text)
    return " ".join(text.split()[:words])


def _ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return round(cov / (va * vb), 3) if va and vb else None


def explain(row, ours, provider, model, words=150, max_docs=4, fresh=False):
    """Ask an AI reviewer why Gemini cited what it cited, comparing the cited
    passages with ours on a rubric, without letting length or markdown count."""
    cited = cited_docs(row)[:max_docs]
    if not cited:
        raise ValueError("None of the cited pages could be imported, so there is no text to compare.")
    queries = [row["prompt"]] + row.get("search_queries", [])[:4]
    me = _Doc("ours", "Danfoss", ours["text"])
    items = [(c["source"].get("domain"), _share(c["source"], row), c["doc"]) for c in cited] + [("our page", 0.0, me)]
    excerpts = [_mask(_excerpt(d, queries, words)) for _, _, d in items]
    n = min(len(e.split()) for e in excerpts)  # the same length for every passage
    excerpts = [" ".join(e.split()[:n]) for e in excerpts]
    order = list(range(len(items)))
    random.Random(hashlib.sha1(row["prompt"].encode()).hexdigest()).shuffle(order)
    labels = {idx: chr(65 + k) for k, idx in enumerate(order)}
    rubric = "\n".join(f"- {k}: {d}" for k, d in RUBRIC)
    user = (f"Question: {row['prompt']}\nSearches the engine ran: {'; '.join(row.get('search_queries', [])) or 'none'}\n\n"
            + "\n\n".join(f"[{labels[idx]}] {excerpts[idx]}" for idx in order))
    key = hashlib.sha256(json.dumps([provider, model, user]).encode()).hexdigest()[:24]
    cache = EXPLAIN_CACHE / f"{key}.json"
    if cache.is_file() and not fresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    text = ai.chat(provider, model, REVIEW_SYSTEM.format(rubric=rubric), user, temperature=0.0,
                   use_cache=not fresh, json_mode=True)
    try:
        data = ai.parse_json(text)
    except (ValueError, json.JSONDecodeError):
        raise ValueError("The reviewer did not answer in the expected format. Try again or pick another model.")
    scores = data.get("scores", {}) or {}
    rows = []
    for idx, (name, share, _) in enumerate(items):
        sc = scores.get(labels[idx], {}) or {}
        vals = {k: max(0, min(2, int(sc.get(k, 0) or 0))) for k, _ in RUBRIC}
        rows.append({"name": name, "label": labels[idx], "gemini_share": round(share, 4), "scores": vals,
                     "total": sum(vals.values()), "excerpt": excerpts[idx]})
    agree = spearman([r["total"] for r in rows], [r["gemini_share"] for r in rows])
    result = {"rows": rows, "why": str(data.get("why", "")), "missing": [str(x) for x in data.get("missing_in_weakest", []) or []],
              "agreement": agree, "words_per_passage": n, "model": f"{provider}/{model}",
              "rubric": [{"key": k, "text": d} for k, d in RUBRIC]}
    EXPLAIN_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return result


# --- from the explanation to wiki suggestions (Natalia's accept/decline flow) ----------------
SUGGEST_DIR = OUT / "suggestions"


def suggestion_folder(run, i, ours_id):
    key = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{pathlib.Path(run).stem}_{i}_{ours_id}")
    return SUGGEST_DIR / key


def suggest(p, run, i, ours, explanation, provider, model, log=print):
    """Wiki changes that would make our next pages answer this prompt's searches the way
    the cited pages do. Uses the reviewer's explanation and the per-search comparison."""
    import analysis
    row = load_run(run)[i]
    cmp = compare(row, ours)
    lost = [f"- \"{q['query']}\": ours {q['our_rank']}/{q['of']}, leader {q['leader']}"
            for q in cmp["queries"] if not q["answered"]]
    scores = "\n".join(
        f"- {r['name']} (Gemini share {r['gemini_share']:.0%}): total {r['total']}/12, "
        + ", ".join(f"{k} {v}" for k, v in r["scores"].items()) for r in explanation.get("rows", []))
    queries = [row["prompt"]] + row.get("search_queries", [])[:4]
    ctx = {"question": row["prompt"], "searches": "; ".join(row.get("search_queries", [])) or "none recorded",
           "scores": scores or "(no reviewer scores)", "why": explanation.get("why", ""),
           "missing": "; ".join(explanation.get("missing", [])) or "-",
           "lost": "\n".join(lost) or "(none: our page is the best match for every search)",
           "ours": _excerpt(_Doc("ours", "Danfoss", ours["text"]), queries, 400)}
    label = f"citations {pathlib.Path(run).stem} · prompt {i + 1}"
    return analysis.suggest_from_citations(p, suggestion_folder(run, i, ours["id"]), label, ctx,
                                           provider, model, log=log)


def load_suggestions(run, i, ours_id):
    import analysis
    return analysis.load(suggestion_folder(run, i, ours_id))


# --- running an update from the app ---------------------------------------------------------
class _LogWriter:
    def __init__(self, log):
        self.log, self.buf = log, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.log(line.rstrip())

    def flush(self):
        pass


def update(prompts, model, log, all_prompts):
    """Ask Gemini (with Google Search) these prompts and import the cited pages:
    the same as `python Run.py update-sources`, with its output in the app's log."""
    import argparse
    disc.load_dotenv()
    import os
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("No Gemini API key. Add it in Settings first.")
    args = argparse.Namespace(model=model, limit=None if all_prompts else len(prompts), sleep=6.0,
                              fresh=False, no_download=False, keep_old=not all_prompts)
    writer = _LogWriter(log)
    try:
        with contextlib.redirect_stdout(writer):
            run_file, rows = disc.run_prompts(prompts, args, key)
            disc.update_sources(rows, run_file, args)
    except SystemExit as e:
        raise RuntimeError(str(e) if e.code not in (None, 0, 1) else
                           "Stopped (quota or network). Progress is saved: press Update again to continue.")
    return run_file.name
