#!/usr/bin/env python3
"""
Review loop for the citation lab: read finished lab runs, find out why Danfoss
loses, and write wiki proposals for a person to approve or reject.

  py lab/review.py lab/results/<normal run> lab/results/<--force-target run>
  py lab/review.py <folders> --provider gemini --model gemini-3.6-flash --sleep 0
  py lab/review.py <folders> --provider fake          offline plumbing test

Step 1  Losses, plain code (no LLM):
        WORDING loss   the Danfoss page was not in BM25's top k. Lists the buyer
                       words from the question that the page lacks, and which
                       higher-ranked pages have them.
        CONTENT loss   the Danfoss page was shown to the AI, but a competitor was
                       recommended, or Danfoss was not cited. Taken from the
                       --force-target run when there is one (the page was always shown).
Step 2  Reviewer "JEV" (LLM): for each content loss, compares the winning
        competitor page with the Danfoss page and ranks the differences. It
        only describes differences; it never states facts about Danfoss.
Step 3  Wiki check (LLM + code): for each difference, is the information already
        in the wiki? The code verifies every wiki line the model quotes.
          yes      -> generator problem (generate_variants.py leaves it out)
          no       -> wiki gap: a proposal marked NEEDS DANFOSS SOURCE
          partly   -> both

Output: lab/review/<date_time>/REVIEW.md, WIKI_PROPOSALS.md, review.json

The LLM class, provider options and answer cache (lab/cache/) come from
experiment.py, so re-running a review costs nothing. This script never edits the
wiki and never reads lab/questions_holdout.txt.
"""
import argparse
import collections
import datetime
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment as lab  # noqa: E402  (reuse: LLM, providers, BM25, page loading)

REPO = lab.REPO
TARGET = lab.TARGET

REVIEWER_SYSTEM = """You are JEV, a reviewer for a citation experiment.
An AI answer engine answered a buyer's question from search results. The Danfoss
page was among the results, but the AI preferred a competitor.

You get: the question, the AI's answer, the WINNING COMPETITOR PAGE and the DANFOSS PAGE.
Task: list the most important differences between the two pages that explain why
the AI preferred the competitor for THIS question, ranked by how much each one
explains the loss (rank 1 = explains the most). At most 5.

Strict rules:
- Only describe differences between the two texts you were given.
- Never state or guess facts about Danfoss products. If the Danfoss page does not
  say something, write that it does not say it; never claim Danfoss lacks or has it.
- Attribute competitor information to the competitor ("the competitor page says ...").
- Do not write marketing text or suggest claims for Danfoss.

Reply with JSON only, no other text:
{"differences": [
  {"rank": 1,
   "topic": "short name of the topic, 2-6 words",
   "competitor_covers": "what the competitor page says about it, paraphrased and attributed",
   "danfoss_page": "missing" or "weak",
   "danfoss_evidence": "exact short quote from the Danfoss page if weak, else empty",
   "why_it_matters": "how this difference shows up in the AI's answer",
   "buyer_words": ["words a buyer would search for this topic"]}
]}"""

REVIEWER_USER = """Question: {question}

AI answer (citations replaced by the page they point to):
{answer}

=== WINNING COMPETITOR PAGE ({brand}) ===
{competitor}

=== DANFOSS PAGE ({page}) ===
{danfoss}"""

JUDGE_SYSTEM = """You check a product knowledge base ("wiki") for a company called Danfoss.
The wiki is the ONLY source allowed for facts on Danfoss web pages. A reviewer
found topics where a competitor page beat a Danfoss page. For each topic, decide
whether the wiki ALREADY contains the information Danfoss would need to cover it.

in_wiki:
  "yes"    the wiki has the information (the Danfoss page just leaves it out or buries it)
  "partly" the wiki has some of it, but not what would close the gap
  "no"     the wiki has nothing usable on this topic

Strict rules:
- wiki_quotes must be lines copied EXACTLY from the wiki below (one line each). If you
  cannot quote it, the answer is not "yes".
- Never invent Danfoss facts. Never turn competitor claims into Danfoss text.
- missing_info: describe what is missing as a question a person must answer from a
  Danfoss document (e.g. "Does the brochure say how ... ?"), never as a statement
  that it is true. No numbers or claims taken from the competitor.
- target_file: the existing wiki file where the missing information belongs, or a
  new path under wiki/<folder>/ if no file fits.
- source_to_check: which Danfoss document or section to look in. The wiki policy
  allows only the eBrochure AD565353287087en-000101; say so if another Danfoss
  document would be needed.
- generator_suggestion: only for yes/partly. What the generated page should cover,
  using ONLY the quoted wiki facts (e.g. "give it its own heading ...").

Reply with JSON only:
{"checks": [
  {"difference_rank": 1, "in_wiki": "yes|partly|no",
   "wiki_files": ["wiki/..."], "wiki_quotes": ["exact line"],
   "generator_suggestion": "", "missing_info": "", "target_file": "wiki/...",
   "source_to_check": ""}
]}"""

JUDGE_USER = """Topics found by the reviewer (question: {question}):
{differences}

=== WIKI (every file, with its path) ===
{wiki}"""


# --- loading -----------------------------------------------------------------
class Run:
    def __init__(self, folder):
        self.folder = pathlib.Path(folder)
        trials = self.folder / "trials.jsonl"
        if not trials.is_file():
            sys.exit(f"{self.folder} has no trials.jsonl: is it a lab results folder?")
        self.rows = [json.loads(l) for l in trials.read_text(encoding="utf-8").splitlines() if l.strip()]
        summary = (self.folder / "summary.md")
        text = summary.read_text(encoding="utf-8") if summary.is_file() else ""
        self.forced = "forced into the results" in text
        m = re.search(r"Model: `([^/`]+)/([^`]+)`", text)
        self.provider, self.model = (m.group(1), m.group(2)) if m else (None, None)
        m = re.search(r"top-(\d+) results", text)
        self.top_k = int(m.group(1)) if m else 5
        m = re.search(r"pages cut to (\d+) words", text)
        self.max_words = int(m.group(1)) if m else 700


def load_wiki(root):
    """{relative path: text without frontmatter}, index/log files left out."""
    root = pathlib.Path(root)
    files = {}
    for p in sorted(root.rglob("*.md")):
        if p.name in {"index.md", "log.md"}:
            continue
        text = p.read_text(encoding="utf-8")
        m = lab.FRONT_RE.match(text)
        files[p.relative_to(REPO).as_posix() if p.is_relative_to(REPO) else p.as_posix()] = (
            text[m.end():] if m else text).strip()
    return files


def norm(s):
    s = re.sub(r"^[\s\-*#>]+", "", s.strip())
    s = re.sub(r"\[\^[^\]]+\]", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_found(quote, wiki):
    q = norm(quote)
    if len(q) < 12:
        return None
    for path, text in wiki.items():
        if q in norm(" ".join(text.split("\n"))) or any(q in norm(l) for l in text.splitlines()):
            return path
    return None


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def ask_json(llm, system, user, key):
    """LLM call with JSON reply; one retry with another cache seed if it does not parse."""
    for attempt in range(2):
        text = llm.ask(system, user, 0.0, 7000 + attempt)
        try:
            return parse_json(text)
        except (ValueError, json.JSONDecodeError):
            print(f"    reply for {key} was not valid JSON" + (", retrying" if attempt == 0 else ", skipped"))
    return None


# --- step 1: wording losses --------------------------------------------------
# Words that phrase the question but carry no topic: not worth adding to a page.
QUESTION_WORDS = set("""gives give makes make choose offer offers use used help helps work
works need needs recommend suggest find get buy pick select should would could""".split())


def near_forms(term, page_terms):
    """Forms of the term the page does use (BM25 here has no stemming:
    'pumps' does not match 'pump')."""
    cands = {term + "s", term + "es", term[:-1] if term.endswith("s") else None,
             term[:-2] if term.endswith("es") else None}
    cands |= set(term.split("-")) if "-" in term else set()
    cands |= {t for t in page_terms if "-" in t and term in t.split("-")}
    return sorted(c for c in cands if c and c != term and c in page_terms)


def term_contrib(bm25, i, term):
    f = bm25.tf[i].get(term, 0)
    if not f:
        return 0.0
    return bm25.idf[term] * f * (bm25.k1 + 1) / (
        f + bm25.k1 * (1 - bm25.b + bm25.b * bm25.len[i] / bm25.avg))


def wording_losses(rows, targets, competitors, top_k, warnings):
    by_q = collections.OrderedDict()
    for r in rows:
        by_q.setdefault(r["question"], []).append(r)
    out = []
    for q, rs in by_q.items():
        lost = [r for r in rs if not r["retrieved"]]
        if not lost:
            continue
        q_terms = list(dict.fromkeys(lab.tokens(q)))
        pages, missing_all = [], collections.Counter()
        for name in sorted({r["page"] for r in lost}):
            target = targets.get(name)
            if target is None:
                warnings.append(f"Page {name} is not on disk any more; wording check skipped for it.")
                continue
            corpus = competitors + [target]
            bm25 = lab.BM25(corpus)
            ranked = bm25.rank(q)
            rank = next(i for i, (_, d) in enumerate(ranked) if d is target) + 1
            stored = {r["bm25_rank"] for r in lost if r["page"] == name}
            if rank not in stored:
                warnings.append(f"{name}: BM25 rank is now {rank}, the run had {sorted(stored)}. "
                                "The pages changed since the run.")
            ti = corpus.index(target)
            above = [d for _, d in ranked[:rank - 1]]
            cutoff = ranked[top_k - 1][1]
            ci = corpus.index(cutoff)
            terms = []
            for t in q_terms:
                mine, theirs = term_contrib(bm25, ti, t), term_contrib(bm25, ci, t)
                holders = [d for d in above if bm25.tf[corpus.index(d)].get(t)]
                terms.append({"term": t, "in_page": bm25.tf[ti].get(t, 0),
                              "danfoss_score": round(mine, 2), "cutoff_score": round(theirs, 2),
                              "pages_above_with_it": [f"{d.brand} ({d.name})" for d in holders],
                              "question_word": t in QUESTION_WORDS,
                              "page_has_form": near_forms(t, bm25.tf[ti])})
            missing = [x["term"] for x in terms if x["in_page"] == 0 and not x["question_word"]]
            missing_all.update(missing)
            pages.append({
                "page": name, "style": target.style, "rank": rank,
                "lost_trials": sum(r["page"] == name for r in lost),
                "score": round(ranked[rank - 1][0], 2), "cutoff_score": round(ranked[top_k - 1][0], 2),
                "cutoff_page": f"{cutoff.brand} ({cutoff.name})",
                "missing_words": missing,
                "question_words_missing": [x["term"] for x in terms
                                           if x["in_page"] == 0 and x["question_word"]],
                "weak_words": [x["term"] for x in terms
                               if x["in_page"] and x["danfoss_score"] < 0.5 * x["cutoff_score"]],
                "terms": terms,
            })
        out.append({"question": q, "lost": len(lost), "total": len(rs),
                    "pages": pages, "missing_words": missing_all.most_common()})
    out.sort(key=lambda w: (-w["lost"] / w["total"], -w["lost"]))
    return out


# --- step 1: content losses --------------------------------------------------
def cites_by_page(row):
    names = {i: v.rsplit(" (", 1)[1].rstrip(")") for i, v in row["context"].items()}
    brands = {i: v.rsplit(" (", 1)[0] for i, v in row["context"].items()}
    ids, _ = lab.parse_answer(row["answer"], {i: True for i in row["context"]})
    return collections.Counter((brands[i], names[i]) for i in ids)


def is_content_loss(row):
    rec = row["recommendation"].strip()
    rec_competitor = bool(rec) and rec.lower() != "none" and TARGET.lower() not in rec.lower()
    return row["in_context"] and (rec_competitor or not row["cited"])


def winner_of(row, comp_brands):
    """(brand, page name) of the competitor that beat Danfoss in this answer."""
    cites = cites_by_page(row)
    rec = row["recommendation"].lower()
    brand = next((b for b in comp_brands if b.lower() in rec), None)
    comp = [(c, bp) for bp, c in cites.items() if bp[0].lower() != TARGET.lower()]
    if brand:
        mine = sorted([(c, bp) for c, bp in comp if bp[0] == brand], reverse=True)
        if mine:
            return mine[0][1]
        page = next((v.rsplit(" (", 1)[1].rstrip(")") for v in row["context"].values()
                     if v.startswith(brand + " (")), None)
        return (brand, page)
    return sorted(comp, reverse=True)[0][1] if comp else (None, None)


def content_losses(rows, comp_brands):
    by_q = collections.OrderedDict()
    for r in rows:
        if r["in_context"]:
            by_q.setdefault(r["question"], []).append(r)
    out = []
    for q, rs in by_q.items():
        lost = [r for r in rs if is_content_loss(r)]
        if not lost:
            continue
        winners = collections.Counter()
        for r in lost:
            r["_winner"] = winner_of(r, comp_brands)
            winners[r["_winner"]] += 1
        styles = collections.Counter(r["style"] for r in lost)
        styles_shown = collections.Counter(r["style"] for r in rs)
        out.append({
            "question": q, "lost": len(lost), "shown": len(rs),
            "winners": [{"brand": b, "page": p, "count": c} for (b, p), c in winners.most_common()],
            "by_style": {s: f"{styles.get(s, 0)}/{n}" for s, n in sorted(styles_shown.items())},
            "original_only": all(r["style"] == "original" for r in lost),
            "rows": lost,
        })
    out.sort(key=lambda c: (-c["lost"] / c["shown"], -c["lost"]))
    return out


def pick_reviews(loss, n, page_share):
    """Losing trials to send to the reviewer: the most common winner page first,
    variant pages before the public original, and the best page overall first
    (what even the best rewrite still misses), one trial per Danfoss page."""
    top_winner = (loss["winners"][0]["brand"], loss["winners"][0]["page"])
    rows = sorted(loss["rows"], key=lambda r: (r["_winner"] != top_winner, r["style"] == "original",
                                                -page_share.get(r["page"], 0), r["page"], r["repeat"]))
    picked, seen = [], set()
    for r in rows:
        if r["page"] in seen or r["_winner"][1] is None:
            continue
        picked.append(r)
        seen.add(r["page"])
        if len(picked) == n:
            break
    return picked


def readable_answer(row):
    def repl(m):
        ids = [c.strip() for c in m.group(1).split(",")]
        return "[" + "; ".join(row["context"].get(i, i) for i in ids) + "]"
    return lab.CITE_RE.sub(repl, row["answer"])


# --- offline stand-ins for --provider fake -------------------------------------
def fake_review(competitor, danfoss):
    mine = set(lab.tokens(danfoss.text))
    counts = collections.Counter(t for t in lab.tokens(competitor.text) if t not in mine and len(t) > 4)
    return {"differences": [
        {"rank": i + 1, "topic": t, "competitor_covers": f"the competitor page uses '{t}' {c} times",
         "danfoss_page": "missing", "danfoss_evidence": "", "why_it_matters": "fake reviewer",
         "buyer_words": [t]} for i, (t, c) in enumerate(counts.most_common(3))]}


def fake_judge(diffs):
    return {"checks": [{"difference_rank": d["rank"], "in_wiki": "no", "wiki_files": [],
                        "wiki_quotes": [], "generator_suggestion": "",
                        "missing_info": f"(fake) Does the brochure cover '{d['topic']}'?",
                        "target_file": "wiki/products/micro-plate-bphe-heat-pumps.md",
                        "source_to_check": "(fake)"} for d in diffs]}


# --- step 3 helpers ------------------------------------------------------------
def clean_target(path, wiki):
    path = (path or "").strip().strip("`").lstrip("/")
    if not path:
        return "wiki/products/micro-plate-bphe-heat-pumps.md", "existing"
    if not path.startswith("wiki/"):
        path = "wiki/" + path
    if not path.endswith(".md"):
        path += ".md"
    return path, ("existing" if (REPO / path).is_file() else "new file")


def leak_warnings(text, comp_brands, comp_pages, wiki_text):
    """Competitor names or figures that slipped into a Danfoss-side proposal."""
    found = [b for b in comp_brands if re.search(rf"\b{re.escape(b)}\b", text, re.IGNORECASE)]
    wiki_nums = set(re.findall(r"\d+(?:[.,]\d+)?", wiki_text))
    comp_nums = set()
    for p in comp_pages:
        comp_nums |= set(re.findall(r"\d+(?:[.,]\d+)?", p.text))
    nums = [n for n in re.findall(r"\d+(?:[.,]\d+)?", text) if n in comp_nums and n not in wiki_nums]
    out = []
    if found:
        out.append("mentions " + ", ".join(found))
    if nums:
        out.append("uses figures from the competitor page (" + ", ".join(sorted(set(nums))) + ")")
    return out


def jaccard(a, b):
    a, b = set(lab.tokens(a)), set(lab.tokens(b))
    return len(a & b) / len(a | b) if a and b else 0.0


def same_generator_issue(a, b):
    """Same root cause: they rest on the same wiki line, or have near-identical topics."""
    qa, qb = {norm(q) for q in a["wiki_quotes"]}, {norm(q) for q in b["wiki_quotes"]}
    return bool(qa & qb) or jaccard(a["topic"], b["topic"]) >= 0.4


def same_gap(a, b):
    """Same missing information: same wiki file and overlapping topic or question."""
    return a["target_file"] == b["target_file"] and (
        jaccard(a["topic"], b["topic"]) >= 0.4 or
        jaccard(a["topic"] + " " + a["missing_info"], b["topic"] + " " + b["missing_info"]) >= 0.2)


def merge(items, same):
    """Merge items that describe the same issue; their scores add up."""
    merged = []
    for it in items:
        for m in merged:
            if same(m, it):
                m["score"] += it["score"]
                m["evidence"] += it["evidence"]
                for f in ("wiki_quotes", "warnings"):
                    m[f] = list(dict.fromkeys(m.get(f, []) + it.get(f, [])))
                break
        else:
            merged.append(dict(it))
    for m in merged:
        m["questions"] = list(dict.fromkeys(e["question"] for e in m["evidence"]))
    return sorted(merged, key=lambda m: -m["score"])


# --- report ----------------------------------------------------------------------
def md_escape(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def show_quote(q):
    """A wiki line for display: no bullet, no footnote marker."""
    q = re.sub(r"\[\^[^\]]+\]", "", q.strip())
    return re.sub(r"^[-*]\s+", "", q).strip()


def sentence(s):
    s = str(s).strip()
    return s if not s or s[-1] in ".!?" else s + "."


def write_review(out, ctx):
    L = [f"# Citation lab review ({ctx['stamp']})", ""]
    for r in ctx["runs"]:
        L.append(f"- Run `{r.folder.as_posix()}`: {'--force-target' if r.forced else 'normal'}, "
                 f"`{r.provider}/{r.model}`, {len(r.rows)} trials")
    L += [f"- Reviewer: `{ctx['reviewer']}`",
          f"- Content losses taken from: {ctx['content_source']}", ""]
    if ctx["fake"]:
        L += ["> **Fake reviewer:** steps 2-3 are placeholders that only test the plumbing.", ""]
    for w in ctx["warnings"]:
        L.append(f"> Warning: {w}")
    if ctx["warnings"]:
        L.append("")
    L += ["## Summary", "",
          f"- **Wording losses** (Danfoss page not in BM25's top {ctx['top_k']}): "
          f"{len(ctx['wording'])} questions",
          f"- **Content losses** (shown, but a competitor was preferred): "
          f"{len(ctx['content'])} questions, {sum(not c['original_only'] for c in ctx['content'])} "
          f"where a rewritten variant lost",
          f"- **Generator problems** (the wiki has it, the variants leave it out): {len(ctx['generator'])}",
          f"- **Wiki gaps** (proposals in WIKI_PROPOSALS.md, all NEEDS DANFOSS SOURCE): {len(ctx['gaps'])}",
          ""]

    L += ["## 1. Wording losses", "",
          "The page never reached the AI. Fix by using the buyer's words (only where the wiki "
          "supports the topic). Ranked by share of trials lost.", "",
          "| # | Question | Lost | Pages not found (rank) | Buyer words missing from the page |",
          "|---|---|---|---|---|"]
    for i, w in enumerate(ctx["wording"], 1):
        pages = ", ".join(f"{p['page']} (#{p['rank']})" for p in w["pages"])
        words = ", ".join(f"{t} ({n})" if n > 1 else t for t, n in w["missing_words"]) or "none (words present but too rare)"
        L.append(f"| W{i} | {md_escape(w['question'])} | {w['lost']}/{w['total']} | {pages} | {words} |")
    for i, w in enumerate(ctx["wording"], 1):
        L += ["", f"### W{i}. {w['question']}", ""]
        for p in w["pages"]:
            L.append(f"- **{p['page']}** ({p['style']}): rank {p['rank']}, BM25 score {p['score']} vs "
                     f"{p['cutoff_score']} for the last page shown ({p['cutoff_page']}).")
            if p["missing_words"]:
                for t in p["terms"]:
                    if t["term"] in p["missing_words"]:
                        holders = ", ".join(t["pages_above_with_it"]) or "no higher page"
                        form = (f" (the page only has `{'`, `'.join(t['page_has_form'])}`: "
                                "the lab's BM25 does not match word forms)") if t["page_has_form"] else ""
                        L.append(f"  - missing `{t['term']}`{form}: used by {holders}")
            if p["question_words_missing"]:
                L.append(f"  - question phrasing only, not worth adding: "
                         f"{', '.join(f'`{x}`' for x in p['question_words_missing'])}")
            if p["weak_words"]:
                L.append(f"  - present but weak: {', '.join(f'`{x}`' for x in p['weak_words'])}")

    L += ["", "## 2. Content losses", "",
          "The AI saw the Danfoss page and still preferred a competitor. Ranked by loss rate.", "",
          "| # | Question | Lost | Winner (times) | Losses by style | Reviewed |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(ctx["content"], 1):
        win = ", ".join(f"{w['brand']} / {w['page']} ({w['count']})" for w in c["winners"][:3])
        styles = ", ".join(f"{s} {v}" for s, v in c["by_style"].items())
        rev = "only the public original lost: not reviewed" if c["original_only"] else \
            ", ".join(f"{r['page']} vs {r['_winner'][1]}" for r in c.get("reviewed", [])) or "-"
        L.append(f"| C{i} | {md_escape(c['question'])} | {c['lost']}/{c['shown']} | {win} | {styles} | {rev} |")

    L += ["", "## 3. Generator problems", "",
          "The wiki already has this information; the variants leave it out or bury it. "
          "Fix in `generate_variants.py` (prompt or styles). Ranked by importance.", ""]
    if not ctx["generator"]:
        L.append("None found.")
    for i, g in enumerate(ctx["generator"], 1):
        L += [f"### G{i}. {g['topic']}", "",
              f"- **Questions lost:** " + "; ".join(g["questions"]),
              f"- **Suggestion for generate_variants.py:** {g['suggestion']}",
              f"- **Wiki already has** ({', '.join(g['wiki_files']) or 'see quotes'}):"]
        L += [f"  - \"{show_quote(q)}\"" for q in g["wiki_quotes"]]
        L.append("- **Evidence:**")
        for e in g["evidence"]:
            L.append(f"  - {e['page']} lost to {e['winner']}: {sentence(e['competitor_covers'])} "
                     f"Danfoss page: {e['danfoss_page']}"
                     + (f" (\"{e['danfoss_evidence']}\")" if e['danfoss_evidence'] else "") + ".")
        L.append("")

    L += ["## 4. Wiki gaps", "",
          "The wiki has nothing (or not enough) on this, so no generator can write it. "
          "Each one is a proposal in WIKI_PROPOSALS.md marked **NEEDS DANFOSS SOURCE**.", ""]
    if not ctx["gaps"]:
        L.append("None found.")
    for i, g in enumerate(ctx["gaps"], 1):
        L += [f"### P{i}. {g['topic']}  (NEEDS DANFOSS SOURCE)", "",
              f"- **Questions lost:** " + "; ".join(g["questions"]),
              f"- **Missing:** {g['missing_info']}",
              f"- **Belongs in:** `{g['target_file']}` ({g['target_status']})",
              f"- **Source to check:** {g['source_to_check']}"]
        for w in g.get("warnings", []):
            L.append(f"- **Check before approving:** the proposal {w}.")
        L.append("- **Evidence:**")
        for e in g["evidence"]:
            L.append(f"  - {e['page']} lost to {e['winner']}: {e['competitor_covers']}")
        L.append("")

    L += ["## Appendix: reviewer output per question", ""]
    for c in ctx["content"]:
        for r in c.get("reviewed", []):
            L += [f"### {c['question']}", "",
                  f"Danfoss page `{r['page']}` vs `{r['_winner'][0]} / {r['_winner'][1]}`, "
                  f"AI recommended: **{r['recommendation'] or 'nothing'}**", "",
                  "AI answer:", ""]
            L += ["> " + line for line in readable_answer(r).splitlines() if line.strip()]
            L.append("")
            for d in r.get("_differences", []):
                L.append(f"{d.get('rank')}. **{d.get('topic')}** ({d.get('danfoss_page')} on the Danfoss page): "
                         f"{d.get('competitor_covers')} *Why:* {d.get('why_it_matters')}")
            L.append("")
    (out / "REVIEW.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_proposals(out, ctx):
    L = [f"# Wiki proposals ({ctx['stamp']})", "",
         "Topics where Danfoss lost and the wiki has no usable information. Nothing here is a "
         "fact: each proposal is a question to answer from a Danfoss document.", "",
         "**How to decide:** tick Approve only if you found the answer in a Danfoss source, "
         "then add it to the wiki yourself with its footnote. Tick Reject if Danfoss has no such "
         "information or it should not be published.", "",
         "**Rules:** every wiki fact comes from the Danfoss eBrochure AD565353287087en-000101 "
         "(`wiki/policies/source-of-truth.md`). Using any other document needs that policy "
         "changed first. The never-claim list still applies. Never copy a competitor's "
         "claims, wording or figures.", ""]
    if ctx["fake"]:
        L += ["> **Fake reviewer:** these proposals are placeholders from an offline test.", ""]
    if not ctx["gaps"]:
        L.append("No wiki gaps found.")
    for i, g in enumerate(ctx["gaps"], 1):
        L += ["---", "", f"## P{i}. {g['topic']}", "",
              "**Status: NEEDS DANFOSS SOURCE**", "",
              "- [ ] Approve: source found (document, page): ____________",
              "- [ ] Reject: reason: ____________", "",
              f"**What is missing:** {g['missing_info']}", "",
              f"**Belongs in:** `{g['target_file']}` ({g['target_status']})", "",
              f"**Danfoss source to look for:** {g['source_to_check']}", ""]
        if g["wiki_quotes"]:
            L.append("**The wiki already has (not enough to close the gap):**")
            L += [f"- \"{show_quote(q)}\"" for q in g["wiki_quotes"]]
            L.append("")
        for w in g.get("warnings", []):
            L += [f"**Check before approving:** this proposal {w}. Rephrase it as a neutral question.", ""]
        L.append(f"**Why it matters:** lost on {len(g['questions'])} question(s):")
        L += [f"- {q}" for q in g["questions"]]
        L += ["", "<details><summary>Evidence (what the winning competitor page covered)</summary>", ""]
        L += [f"- {e['winner']}: {e['competitor_covers']}" for e in g["evidence"]]
        L += ["", "</details>", ""]
    (out / "WIKI_PROPOSALS.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --- main ------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", help="lab results folders (normal and/or --force-target)")
    ap.add_argument("--provider", choices=lab.PROVIDERS, default="gemini")
    ap.add_argument("--model", help="default: the model the runs used (same provider), else the provider default")
    ap.add_argument("--host", help="Ollama address, e.g. http://localhost:11434")
    ap.add_argument("--sleep", type=float, help="seconds between API calls (default 6 for gemini, 0 otherwise)")
    ap.add_argument("--variants", nargs="+",
                    default=[str(REPO / "variants ManuJuan"), str(HERE / "corpus" / "danfoss_original")])
    ap.add_argument("--competitors", default=str(HERE / "corpus" / "competitors"))
    ap.add_argument("--wiki", default=str(REPO / "wiki"))
    ap.add_argument("--reviews-per-question", type=int, default=1,
                    help="losing Danfoss pages to review per question (one LLM call each)")
    ap.add_argument("--out", default=str(HERE / "review"))
    args = ap.parse_args()

    lab.load_dotenv()
    runs = [Run(f) for f in args.runs]
    normal = [r for r in runs if not r.forced]
    forced = [r for r in runs if r.forced]
    top_k = runs[0].top_k
    max_words = runs[0].max_words
    warnings = []
    if len({(r.top_k, r.max_words) for r in runs}) > 1:
        warnings.append("The runs used different top-k or page lengths; using the first run's settings.")

    targets = {d.name: d for f in args.variants for d in lab.load_docs(f, TARGET, max_words)
               if d.brand.lower() == TARGET.lower()}
    competitors = [d for d in lab.load_docs(args.competitors, "unknown", max_words)
                   if d.brand.lower() != TARGET.lower()]
    comp_by_name = {d.name: d for d in competitors}
    comp_brands = sorted({d.brand for d in competitors}, key=len, reverse=True)
    wiki = load_wiki(args.wiki)
    wiki_text = "\n".join(wiki.values())

    # step 1
    wording_rows = [r for run in (normal or forced) for r in run.rows]
    wording = wording_losses(wording_rows, targets, competitors, top_k, warnings)
    content_rows = [r for run in (forced or normal) for r in run.rows]
    content_source = ("the --force-target run (page always shown)" if forced else
                      "the normal run, only trials where the page was shown (no --force-target run given)")
    content = content_losses(content_rows, comp_brands)
    print(f"Step 1: {len(wording)} questions with wording losses, {len(content)} with content losses")

    # steps 2-3
    fake = args.provider == "fake"
    llm = None
    if not fake:
        model = args.model or next((r.model for r in runs if r.provider == args.provider), None)
        sleep = args.sleep if args.sleep is not None else (6.0 if args.provider == "gemini" else 0.0)
        llm = lab.LLM(args.provider, model, args.host, sleep, HERE / "cache")
    reviewer = "fake" if fake else f"{args.provider}/{llm.model}"
    wiki_block = "\n\n".join(f"--- {p} ---\n{t}" for p, t in wiki.items())

    shares = collections.defaultdict(list)
    for r in content_rows:
        shares[r["page"]].append(r["share"])
    page_share = {p: sum(v) / len(v) for p, v in shares.items()}

    gen_items, gap_items = [], []
    todo = [c for c in content if not c["original_only"]]
    for ci, c in enumerate(todo, 1):
        c["reviewed"] = pick_reviews(c, args.reviews_per_question, page_share)
        weight = c["lost"] / c["shown"]
        for row in c["reviewed"]:
            danfoss = targets.get(row["page"])
            comp = comp_by_name.get(row["_winner"][1])
            if danfoss is None or comp is None:
                warnings.append(f"Skipped review of '{c['question']}': page {row['page']} or "
                                f"{row['_winner'][1]} is not on disk any more.")
                continue
            print(f"Step 2 [{ci}/{len(todo)}] JEV: {row['page']} vs {comp.brand}/{comp.name}", flush=True)
            if fake:
                review = fake_review(comp, danfoss)
            else:
                review = ask_json(llm, REVIEWER_SYSTEM, REVIEWER_USER.format(
                    question=c["question"], answer=readable_answer(row), brand=comp.brand,
                    competitor=comp.text, page=danfoss.name, danfoss=danfoss.text), "JEV")
            diffs = [d for d in (review or {}).get("differences", []) if isinstance(d, dict)][:5]
            for i, d in enumerate(diffs, 1):
                d["rank"] = int(d.get("rank") or i)
                d["topic"] = str(d.get("topic") or f"difference {i}")
            row["_differences"] = diffs
            if not diffs:
                warnings.append(f"No usable reviewer output for '{c['question']}'.")
                continue

            print(f"Step 3 [{ci}/{len(todo)}] wiki check of {len(diffs)} differences", flush=True)
            listing = "\n".join(f"{d['rank']}. {d['topic']}: {d.get('competitor_covers', '')} "
                                f"(Danfoss page: {d.get('danfoss_page', '')})" for d in diffs)
            judged = fake_judge(diffs) if fake else ask_json(
                llm, JUDGE_SYSTEM, JUDGE_USER.format(question=c["question"], differences=listing,
                                                     wiki=wiki_block), "wiki check")
            checks = {int(k.get("difference_rank", 0)): k for k in (judged or {}).get("checks", [])
                      if isinstance(k, dict)}
            for d in diffs:
                k = checks.get(d["rank"], {"in_wiki": "no"})
                verdict = str(k.get("in_wiki", "no")).lower()
                quotes, files = [], []
                for q in k.get("wiki_quotes") or []:
                    path = quote_found(str(q), wiki)
                    if path:
                        quotes.append(str(q).strip())
                        files.append(path)
                if verdict == "yes" and not quotes:
                    verdict = "no"
                    warnings.append(f"'{d['topic']}': the wiki check said the wiki has it, but none of "
                                    "its quotes are in the wiki. Treated as a wiki gap.")
                elif verdict == "partly" and not quotes:
                    verdict = "no"
                evidence = {"question": c["question"], "page": row["page"],
                            "winner": f"{comp.brand} ({comp.name})",
                            "competitor_covers": str(d.get("competitor_covers", "")).strip(),
                            "danfoss_page": d.get("danfoss_page", ""),
                            "danfoss_evidence": str(d.get("danfoss_evidence", "")).strip()}
                score = weight * c["lost"] / d["rank"]
                if verdict in ("yes", "partly"):
                    gen_items.append({
                        "topic": d["topic"], "score": score, "evidence": [evidence],
                        "suggestion": str(k.get("generator_suggestion") or
                                          "Cover this topic using the quoted wiki facts.").strip(),
                        "wiki_quotes": quotes, "wiki_files": sorted(set(files))})
                if verdict in ("partly", "no"):
                    target, status = clean_target(k.get("target_file"), wiki)
                    missing = str(k.get("missing_info") or f"What does Danfoss say about {d['topic']}?").strip()
                    source = str(k.get("source_to_check") or
                                 "Danfoss eBrochure AD565353287087en-000101").strip()
                    gap_items.append({
                        "topic": d["topic"], "score": score, "evidence": [evidence],
                        "missing_info": missing, "source_to_check": source,
                        "target_file": target, "target_status": status,
                        "wiki_quotes": quotes,
                        "warnings": leak_warnings(missing + " " + source, comp_brands, [comp], wiki_text)})

    generator = merge(gen_items, same_generator_issue)
    for g in generator:
        g["wiki_files"] = sorted({f for q in g["wiki_quotes"] for f in [quote_found(q, wiki)] if f})
    gaps = merge(gap_items, same_gap)

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = pathlib.Path(args.out) / stamp
    out.mkdir(parents=True, exist_ok=True)
    ctx = {"stamp": stamp, "runs": runs, "reviewer": reviewer, "fake": fake, "top_k": top_k,
           "content_source": content_source, "warnings": list(dict.fromkeys(warnings)),
           "wording": wording, "content": content, "generator": generator, "gaps": gaps}
    write_review(out, ctx)
    write_proposals(out, ctx)
    dump = {k: v for k, v in ctx.items() if k not in {"runs", "content"}}
    dump["runs"] = [{"folder": r.folder.as_posix(), "forced": r.forced, "model": f"{r.provider}/{r.model}"}
                    for r in runs]
    dump["content"] = [{**{k: v for k, v in c.items() if k not in {"rows", "reviewed"}},
                        "reviewed": [{"page": r["page"], "winner": list(r["_winner"]),
                                      "differences": r.get("_differences", [])}
                                     for r in c.get("reviewed", [])]} for c in content]
    (out / "review.json").write_text(json.dumps(dump, indent=2, ensure_ascii=False, default=str),
                                     encoding="utf-8")
    if llm:
        print(f"API calls: {llm.calls}, from cache: {llm.hits}")
    print(f"Saved in {out}  (REVIEW.md, WIKI_PROPOSALS.md, review.json)")
    print(f"{len(generator)} generator problems, {len(gaps)} wiki gaps (all NEEDS DANFOSS SOURCE)")


if __name__ == "__main__":
    main()
