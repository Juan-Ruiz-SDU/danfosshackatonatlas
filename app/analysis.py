"""
Citation targets, and wiki suggestions when a run misses them.

After every run the best version of the new set of pages is checked against the
product's targets: Danfoss cited in at least X% of the answers, and cited first in
at least N answers (a count: a percentage swings too much with few questions).

If either target is missed, an AI (Ollama qwen3:8b by default) compares the best and
the worst Danfoss version of that set, question by question, and proposes changes to
the wiki so the next set of pages does better. The wiki is the single source of truth,
so nothing is changed until a person accepts a suggestion in the app. Accepted changes
are written to the wiki file and noted in wiki/log.md.

Everything is read from the run folder, so the analysis can be run again later
(e.g. if the Ollama server was off) without repeating the run.
"""
import collections
import datetime
import json
import pathlib
import re

import ai
import products

APP = pathlib.Path(__file__).resolve().parent
TARGETS_FILE = APP / "targets.json"
BUILTIN_TARGETS = {"cited_pct": 50, "first_count": 4}
ANALYST = ("ollama", "qwen3:8b")
# The analysis uses the same context size as every other step (num_ctx in
# providers.json, 16384): asking for a bigger one makes Ollama reload the model, which
# can drop a request already running on the shared server. The prompt is trimmed to fit.
ANSWER_TOKENS = 2500      # room left for the answer
CHARS_PER_TOKEN = 3.0     # careful estimate for Markdown with many figures
WIKI_BUDGET = 36000       # most characters of wiki shown to the AI
PAGE_BUDGET = 4500        # characters of each page shown
FILE_BUDGET = 5000        # per file
SKIP_FILES = re.compile(r"(^|/)(index|log)\.md$|^experiments/")
DANFOSS = "danfoss"


# --- targets ---------------------------------------------------------------------
def _clean_targets(t):
    out = {}
    if t.get("cited_pct") not in (None, ""):
        v = float(t["cited_pct"])
        if not 0 <= v <= 100:
            raise ValueError("The citation target must be between 0 and 100 %")
        out["cited_pct"] = int(v) if v == int(v) else v
    if t.get("first_count") not in (None, ""):
        v = int(float(t["first_count"]))
        if v < 0:
            raise ValueError("The 'cited first' target cannot be negative")
        out["first_count"] = v
    return out


def default_targets():
    try:
        saved = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**BUILTIN_TARGETS, **_clean_targets(saved)}


def set_default_targets(t):
    TARGETS_FILE.write_text(json.dumps({**default_targets(), **_clean_targets(t)}, indent=2) + "\n",
                            encoding="utf-8")


def product_targets(p):
    own = _clean_targets(p.get("targets") or {})
    return {**default_targets(), **own, "custom": bool(own)}


def set_product_targets(p, t, reset=False):
    path = p["folder"] / "product.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if reset:
        data.pop("targets", None)
    else:
        data["targets"] = {**_clean_targets(data.get("targets") or {}), **_clean_targets(t)}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check(win, targets):
    """win: the best version's summary row (needs trials, cited_count, first_count)."""
    cited_pct = 100 * win["cited_count"] / win["trials"] if win["trials"] else 0
    c = {"cited_target": targets["cited_pct"], "first_target": targets["first_count"],
         "cited_pct": round(cited_pct, 1), "first_count": win["first_count"],
         "trials": win["trials"]}
    c["cited_ok"] = cited_pct >= targets["cited_pct"]
    c["first_ok"] = win["first_count"] >= targets["first_count"]
    c["met"] = c["cited_ok"] and c["first_ok"]
    return c


def check_text(c):
    def mark(ok):
        return "met" if ok else "MISSED"
    return (f"Cited in {c['cited_pct']:g}% of {c['trials']} answers (target {c['cited_target']:g}%: "
            f"{mark(c['cited_ok'])}); cited first in {c['first_count']} (target {c['first_target']}: "
            f"{mark(c['first_ok'])}).")


# --- wiki files -------------------------------------------------------------------------
def wiki_files(p):
    """{relative path: file} of the wiki files a suggestion may change."""
    path = products.wiki_dir(p)
    if path.is_file():
        return {path.name: path}
    if not path.is_dir():
        return {}
    out = {}
    for f in sorted(path.rglob("*.md")):
        rel = f.relative_to(path).as_posix()
        if not SKIP_FILES.search(rel):
            out[rel] = f
    return out


def _wiki_for_prompt(files, budget=WIKI_BUDGET):
    # guidelines first: they decide how every page is written
    order = sorted(files, key=lambda r: (not r.startswith("guidelines/"), r))
    parts, used = [], 0
    for rel in order:
        text = files[rel].read_text(encoding="utf-8", errors="replace").strip()
        if len(text) > FILE_BUDGET:
            text = text[:FILE_BUDGET] + "\n[... rest of the file not shown]"
        if used + len(text) > budget:
            parts.append(f"=== FILE: {rel} ===\n[not shown: out of room]")
            continue
        used += len(text)
        parts.append(f"=== FILE: {rel} ===\n{text}")
    return "\n\n".join(parts)


def _log_file(p):
    path = products.wiki_dir(p)
    return path / "log.md" if path.is_dir() and (path / "log.md").is_file() else None


# --- the analysis -----------------------------------------------------------------------
PROMPT = """You improve a product wiki so that the web pages an AI writes from it get cited more
often, and cited FIRST more often, in Google's AI answers to buyer questions.

How it works: an AI writer writes Danfoss product pages using ONLY this wiki. Fact files hold
the product facts. Guideline files (in guidelines/, "type: Guideline") tell the writer how to
write. Each run writes a set of page versions; each version is then tested: a search engine picks
the top pages for each buyer question, and Google's AI answers the question and cites sources.

PRODUCT: {product}
TARGETS: Danfoss cited in at least {cited_target}% of answers, and cited first in at least
{first_target} answers.
RESULT OF THE BEST VERSION: {check}

BEST VERSION ("{best_name}"): cited in {best_cited} of {trials} answers, cited first {best_first} times.
--- BEST PAGE ---
{best_page}
--- END ---

WORST VERSION ("{worst_name}"): cited in {worst_cited} of {trials} answers, cited first {worst_first} times.
--- WORST PAGE ---
{worst_page}
--- END ---

QUESTION BY QUESTION (cited = Danfoss page cited; "first instead" = who was cited first):
{per_question}

THE WIKI (every file a change may edit):
{wiki}

YOUR TASK: compare the best and the worst page. What does the best page do that the worst does
not (direct answer at the start, product type named, figures, structure, headings that match the
questions, answering the buyer question asked)? Where were both pages beaten, and by whom? Then
propose changes to the wiki so that EVERY new page does more of what works.

RULES:
- Only use facts that are already in the wiki. Never invent figures, models, certifications,
  quotes, prices or claims. Never copy anything from competitors.
- Prefer changes to guideline files (how to write) and making existing facts clearer, more
  complete or easier to find (e.g. a short summary line that repeats facts already in the file).
- A change is "replace" (copy the exact text now in the file into "find", put the new text in
  "text") or "add" (new text added at the end of the file; leave "find" empty).
- "file" must be one of the file names shown above, e.g. "guidelines/page-structure.md".
- If buyers ask about something the wiki has no fact for, list it in "missing_facts"
  (a person must find a Danfoss source). Do not write it into a change.
- Give 2 to 6 changes, most useful first.

Return ONLY a JSON object:
{{"diagnosis": "two or three sentences on why the target was missed",
  "best_does": ["what the best page does well"],
  "worst_misses": ["what the worst page lacks"],
  "changes": [{{"file": "...", "action": "add or replace", "find": "", "text": "...",
               "why": "what this changes in the next pages"}}],
  "missing_facts": ["..."]}}
"""


def _rows(out):
    path = out / "citation_test.jsonl"
    if not path.is_file():
        raise ValueError("This run has no citation test results")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _stats(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["style"]].append(r)
    out = {}
    for style, rs in by.items():
        n = len(rs)
        out[style] = {"trials": n, "cited_count": sum(r["cited"] for r in rs),
                      "first_count": sum(r["first"] for r in rs),
                      "share": sum(r["share"] for r in rs) / n}
    return out


def _per_question(rows, best, worst):
    qs = list(dict.fromkeys(r["question"] for r in rows))
    lines = []
    for i, q in enumerate(qs, 1):
        def desc(style):
            rs = [r for r in rows if r["style"] == style and r["question"] == q]
            if not rs:
                return "-"
            c, f = sum(r["cited"] for r in rs), sum(r["first"] for r in rs)
            rivals = collections.Counter(r["cited_brands"][0] for r in rs
                                         if r["cited_brands"] and not r["first"])
            s = ("first" if f else "cited" if c else "NOT cited") + (f" {c}/{len(rs)}" if len(rs) > 1 else "")
            if rivals:
                s += " (first instead: " + ", ".join(b for b, _ in rivals.most_common(2)) + ")"
            return s
        lines.append(f"{i}. {q}\n   best: {desc(best)} | worst: {desc(worst)}")
    return "\n".join(lines)


def _page_text(p, out, style, rows):
    f = out / "variants" / f"{style}.md"
    if f.is_file():
        return f.read_text(encoding="utf-8", errors="replace").strip()
    name = next((r["page"] for r in rows if r["style"] == style), None)
    import pipeline  # late: pipeline imports this module
    for d in pipeline.load_pages(p, 2000):
        if d.name == name:
            return d.text
    return "(page text not found)"


def _ask(job, provider, model, prompt):
    p = ai.providers().get(provider)
    if not p:
        raise RuntimeError(f"Unknown AI '{provider}' for the wiki analysis. Check Settings.")
    if p.get("type") != "ollama":
        return ai.chat(provider, model, "", prompt, temperature=0.2, cancel=job.cancelled,
                       use_cache=False, log=job.log)
    reachable, _ = ai.ollama_status(p["base_url"])
    if not reachable:
        raise RuntimeError(f"Cannot reach Ollama at {p['base_url']} for the wiki analysis. "
                           "When it is back, press 'Try the analysis again'.")
    expected = 1500

    def on_token(n):
        nonlocal expected
        expected = max(expected, int(n * 1.1))
        job.step("Analysing the pages to improve the wiki", n, expected)
    job.step("Analysing the pages to improve the wiki", 0, expected)
    for attempt in range(2):
        try:
            text, _ = ai.ollama_stream(provider, model, "", prompt, temperature=0.2, fmt="json",
                                       on_token=on_token, cancel=job.cancelled)
            return text
        except ai.ConnectionLost as e:
            if attempt:
                raise
            job.log(f"  {e} Asking again ...")


def _norm_file(name, files):
    name = (name or "").strip().strip("`").replace("\\", "/")
    name = re.sub(r"^(\./)?(wiki/)?", "", name)
    if name in files:
        return name
    hits = [r for r in files if r.endswith("/" + name) or r == name + ".md"]
    return hits[0] if len(hits) == 1 else None


def _clean_changes(raw, files, allowed):
    import pipeline
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        rel = _norm_file(c.get("file"), files)
        text = str(c.get("text") or "").strip()
        if not rel or not text:
            continue
        action = "replace" if str(c.get("action", "")).lower().startswith("rep") else "add"
        find = str(c.get("find") or "").strip()
        note = ""
        if action == "replace":
            current = files[rel].read_text(encoding="utf-8", errors="replace")
            if not find or find not in current:
                action, find = "add", ""
                note = "The AI's text to replace was not found exactly, so this is added at the end of the file instead."
        new_numbers = sorted(pipeline.gv.norm_numbers(text) - allowed, key=len) if allowed else []
        out.append({"id": f"s{len(out) + 1}", "file": rel, "action": action, "find": find,
                    "text": text, "why": str(c.get("why") or "").strip(), "note": note,
                    "unknown_numbers": new_numbers, "decision": None})
    return out


def analyse(job, p, out):
    """Run the analysis for one finished run folder. Writes wiki_suggestions.json/.md."""
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    settings = json.loads((out / "settings.json").read_text(encoding="utf-8"))
    rows = _rows(out)
    stats = _stats(rows)
    best = result["winner"]["style"]
    generated = [s for s in settings.get("styles", []) if s in stats and (out / "variants" / f"{s}.md").is_file()]
    others = [s for s in generated if s != best]
    rank = lambda s: (stats[s]["share"], stats[s]["cited_count"], stats[s]["first_count"])  # noqa: E731
    if others:
        worst = min(others, key=rank)
    elif "original" in stats:
        worst = "original"  # only one version written: compare with today's Danfoss page
    else:
        raise ValueError("Only one page version was tested, so there is nothing to compare. "
                         "Tick at least two page versions in the Run card.")
    import pipeline
    names = pipeline.STYLE_NAMES
    targets = result.get("targets") or check(stats[best], product_targets(p))
    files = wiki_files(p)
    if not files:
        raise ValueError("No wiki files found for this product")
    try:
        allowed = pipeline.gv.allowed_numbers(products.fact_sheet(p))
    except ValueError:
        allowed = frozenset()

    fields = dict(
        product=p["name"], cited_target=targets["cited_target"], first_target=targets["first_target"],
        check=check_text(targets), trials=stats[best]["trials"],
        best_name=names.get(best, best), best_cited=stats[best]["cited_count"],
        best_first=stats[best]["first_count"], best_page=_page_text(p, out, best, rows)[:PAGE_BUDGET],
        worst_name=names.get(worst, worst), worst_cited=stats[worst]["cited_count"],
        worst_first=stats[worst]["first_count"], worst_page=_page_text(p, out, worst, rows)[:PAGE_BUDGET],
        per_question=_per_question(rows, best, worst))
    provider, model = settings.get("analyst") or ANALYST[0], settings.get("analyst_model") or ANALYST[1]
    pinfo = ai.providers().get(provider, {})
    budget = WIKI_BUDGET
    if pinfo.get("type") == "ollama":  # fit the prompt into the server's context size
        room = (int(pinfo.get("num_ctx", 16384)) - ANSWER_TOKENS) * CHARS_PER_TOKEN
        budget = int(min(WIKI_BUDGET, max(4000, room - len(PROMPT.format(**fields, wiki="")))))
    prompt = PROMPT.format(**fields, wiki=_wiki_for_prompt(files, budget))

    job.log(f"Wiki analysis with {provider} {model}: best '{names.get(best, best)}' vs worst "
            f"'{names.get(worst, worst)}'")
    last = None
    for attempt in range(2):
        if attempt:
            job.log(f"  asking again ({last})")
        answer = _ask(job, provider, model, prompt)
        try:
            d = ai.parse_json(answer)
            changes = _clean_changes(d.get("changes"), files, allowed)
            if not changes:
                raise ValueError("no usable changes (each needs a wiki file name and a text)")
            break
        except ValueError as e:
            last = str(e)
    else:
        raise RuntimeError(f"The AI's analysis could not be used: {last}")

    def strings(v):
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []
    data = {"status": "ready", "run": out.name, "check": targets, "analyst": f"{provider} {model}",
            "best": {"style": best, "name": names.get(best, best), **stats[best]},
            "worst": {"style": worst, "name": names.get(worst, worst), **stats[worst]},
            "diagnosis": str(d.get("diagnosis") or "").strip(),
            "best_does": strings(d.get("best_does")), "worst_misses": strings(d.get("worst_misses")),
            "missing_facts": strings(d.get("missing_facts")), "suggestions": changes}
    save(out, data)
    job.log(f"  {len(changes)} wiki suggestions ready: accept or decline them in Results")
    return data


# --- saving, accepting, declining ---------------------------------------------------------
def load(out):
    f = out / "wiki_suggestions.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def save(out, data):
    (out / "wiki_suggestions.json").write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    (out / "wiki_suggestions.md").write_text(markdown(data), encoding="utf-8")


def markdown(d):
    L = [f"# Wiki suggestions · run {d['run']}", "", check_text(d["check"]), "",
         f"Compared: best version **{d['best']['name']}** with worst **{d['worst']['name']}** "
         f"(analysis by {d['analyst']}).", "", d["diagnosis"], ""]
    if d["best_does"]:
        L += ["**The best page:**"] + [f"- {x}" for x in d["best_does"]] + [""]
    if d["worst_misses"]:
        L += ["**The worst page lacks:**"] + [f"- {x}" for x in d["worst_misses"]] + [""]
    L += ["## Suggested changes", ""]
    for s in d["suggestions"]:
        state = {"accepted": "ACCEPTED", "declined": "declined"}.get(s["decision"], "waiting")
        L += [f"### {s['id']}. `{s['file']}` ({s['action']}) · {state}", "", s["why"], ""]
        if s["find"]:
            L += ["Replace:", "", "> " + s["find"].replace("\n", "\n> "), "", "With:", ""]
        L += ["> " + s["text"].replace("\n", "\n> "), ""]
        if s["unknown_numbers"]:
            L += [f"Check: numbers not in the wiki: {', '.join(s['unknown_numbers'])}", ""]
    if d["missing_facts"]:
        L += ["## Missing facts (need a Danfoss source)", ""] + [f"- {x}" for x in d["missing_facts"]]
    return "\n".join(L) + "\n"


def decide(p, out, sid, decision, text=None):
    d = load(out)
    if not d:
        raise ValueError("This run has no wiki suggestions")
    s = next((x for x in d["suggestions"] if x["id"] == sid), None)
    if not s:
        raise ValueError("Unknown suggestion")
    if s["decision"]:
        raise ValueError(f"This suggestion was already {s['decision']}")
    if decision not in ("accept", "decline"):
        raise ValueError("Accept or decline")
    if decision == "accept":
        if text is not None and text.strip():
            s["text"] = text.strip()  # the person may have edited it
        files = wiki_files(p)
        if s["file"] not in files:
            raise ValueError(f"The wiki file {s['file']} no longer exists")
        f = files[s["file"]]
        current = f.read_text(encoding="utf-8")
        if s["action"] == "replace":
            if s["find"] not in current:
                raise ValueError("The text to replace is no longer in the file (the wiki changed). "
                                 "Decline this one, or change the file by hand.")
            new = current.replace(s["find"], s["text"], 1)
        else:
            new = current.rstrip() + "\n\n" + s["text"] + "\n"
        f.write_text(new, encoding="utf-8")
        _log(p, d["run"], s)
    s["decision"] = "accepted" if decision == "accept" else "declined"
    s["decided"] = datetime.datetime.now().isoformat(timespec="seconds")
    save(out, d)
    return d


def _log(p, run, s):
    """Note the change in wiki/log.md, newest first under today's date, like the team does."""
    f = _log_file(p)
    if not f:
        return
    today = datetime.date.today().isoformat()
    entry = (f"* **Update** (wiki suggestion {s['id']} from run `{run}`, accepted in the Atlas app): "
             f"`{s['file']}` ({'text replaced' if s['action'] == 'replace' else 'text added'}). "
             f"{s['why']}")
    lines = f.read_text(encoding="utf-8").splitlines()
    head = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
    if head is not None and lines[head].strip() == f"## {today}":
        lines.insert(head + 1, entry)
    else:
        at = head if head is not None else len(lines)
        lines[at:at] = [f"## {today}", entry, ""]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
