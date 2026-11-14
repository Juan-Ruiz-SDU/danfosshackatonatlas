"""
Section-by-section writing with assigned evidence and verified [id] citations.

The 2026 way to write a grounded page with a small local model (WebWeaver,
WriteHERE, OmniThink; the CLEF 2026 CheckThat! fact-check articles):

  1. Sub-queries   The searches the page must answer. In order of trust:
                   - the searches Gemini really ran (Citations tab, webSearchQueries),
                   - the product's buyer questions (Run tab),
                   - a fan-out by the writer AI, only if there are too few.
                   Near-duplicates are merged.
  2. Evidence      Every wiki fact line gets an id [w12]; every original passage in
                   raw/ gets [r7]. Each sub-query gets its own evidence:
                   BM25 + embeddings (RRF), then a reranker (app/retrieval.py).
                   A sub-query with no evidence that answers it gets no section:
                   it is listed as a missing fact instead of being padded.
  3. Writing       One section per sub-query, with ONLY its evidence in the prompt.
                   The heading matches the search; the first sentence answers it;
                   every factual sentence cites its evidence id while it is written
                   (adding citations afterwards fails with 1-8B models).
  4. Verification  Each sentence is checked against the evidence it cites:
                   copied? -> numbers in the cited evidence? -> grounding check
                   (MiniCheck if installed, otherwise the AI must quote the evidence,
                   and the quote is checked in code). Unsupported sentences get one
                   rewrite with feedback; what still fails is removed.
  5. The page      Title + short answer + the sections. Saved twice: with the [id]
                   citations (for review) and clean (for publishing and the lab).

Everything the steps did is saved as process.json, which the app's "How it works"
tab draws.
"""
import json
import re

import ai
import products
import retrieval
import verify

gv = verify.gv
CITE_RE = re.compile(r"\s*\[((?:[wr]\d+)(?:\s*,\s*[wr]\d+)*)\]")
WORD_RE = re.compile(r"[a-z0-9]+")

SECTION_PROMPT = """You write ONE section of a product web page about: {topic}.
This section answers the search: "{query}"

Rules:
- Start with a level-2 heading ("## ...") that says what the search asks, in plain words.
- The first sentence answers the search directly.
- Use ONLY the evidence below. Never add a fact, figure, model name, certification or
  claim that is not in it. If the evidence only partly answers, say only that part.
- After EVERY sentence that states a fact, put the id of the evidence it comes from in
  square brackets, e.g. "... up to 10 bar [w3]." Only use the ids listed below.
- At most {words} words. Plain and specific. No superlatives ("best", "leading").
{guidelines}
EVIDENCE:
{evidence}

Write the section now (Markdown, no preamble):"""

INTRO_PROMPT = """You write the start of a product web page about: {topic}.

Write:
- a level-1 title ("# ...") that names the product and what it is for;
- then 2 or 3 sentences that say what it is, who it is for and its main benefit.
Use ONLY the evidence below and put its id in square brackets after every factual
sentence, e.g. "... for heat pumps [w2]." At most {words} words. No superlatives.

EVIDENCE:
{evidence}

Write it now (Markdown, no preamble):"""

FIX_PROMPT = """The section below has sentences that its cited evidence does not support:
{problems}

Rewrite the section so every sentence is supported by the evidence it cites: correct
those sentences or remove them. Keep the heading, keep the other sentences and their
[id] citations. Same rules: only the evidence below, cite [id] after every fact.

EVIDENCE:
{evidence}

SECTION:
{section}

Rewritten section (Markdown, no preamble):"""

BATCH_CHECK = """You check whether each CLAIM is supported by the EVIDENCE it cites.
Supported = everything the claim states is in that evidence (paraphrase is fine).
Partly = some of it. Unsupported = the evidence does not say it, or says something else.
Use only the evidence, not your own knowledge.

Reply with JSON only:
{"claims": {"<claim number>": {"verdict": "supported" | "partly" | "unsupported",
  "quote": "exact words copied from the evidence that support it, or empty"}}}"""

FANOUT_PROMPT = """A buyer asks Google about: {topic}.
Google's AI splits such a question into several web searches before it answers.
List {n} different searches it would run (short, specific, in English), covering
what the product is, how it works, specifications, applications, comparisons and
buying questions. Reply with JSON only: {{"searches": ["...", "..."]}}"""


# --- 1. evidence units --------------------------------------------------------------------
def evidence_units(p, sheet):
    """Wiki fact lines as [w1..], raw/ passages as [r1..]. Table rows are read as
    'Header: value; Header: value' so a row stands on its own."""
    units, title, header = [], "wiki", None
    lines = []  # the wiki wraps long lines: join a continuation line to its bullet or sentence
    for line in gv.facts_only(sheet).splitlines():
        s = line.strip()
        if (s and lines and lines[-1] and not re.match(r"[-*#|>]|\d+\.\s", s)
                and not lines[-1].startswith(("#", "|"))):
            lines[-1] += " " + s
        else:
            lines.append(s)
    for s in lines:
        if s.startswith("#"):
            title, header = s.lstrip("# ").strip(), None
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue
            if header is None:
                header = cells
                continue
            s = "; ".join(f"{h}: {c}" for h, c in zip(header, cells) if c)
        else:
            header = None
            s = s.lstrip("-*> ").strip()
        if len(s.split()) >= 3:
            units.append(retrieval.Unit(f"w{len(units) + 1}", f"wiki: {title}", s))
    n = 0
    for sid, head, text in (gv.raw_passages(products.REPO / p["raw_dir"]) if p.get("raw_dir") else []):
        n += 1
        units.append(retrieval.Unit(f"r{n}", f"raw: {sid}", (head + ": " + text).strip(": ")))
    return units


# --- 2. sub-queries -------------------------------------------------------------------------
def _words(s):
    return set(WORD_RE.findall(s.lower())) - {"the", "a", "an", "of", "for", "and", "to", "in", "is", "what", "how", "which", "do", "does"}


def _similar(a, b):
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def gemini_searches(p):
    """The searches Gemini ran for prompts about this product, newest run first
    (recorded by the Citations tab). Only prompts that share words with the product."""
    try:
        import citations
        runs = citations.list_runs()
    except Exception:  # noqa: BLE001
        return []
    topic = _words(" ".join(x for x in (p.get("name"), p.get("product_type"), p.get("application")) if x))
    out = []
    for run in reversed(runs[-3:]):
        for row in citations.load_run(run.name):
            if len(_words(row.get("prompt", "")) & topic) >= 2:
                out += [q for q in row.get("search_queries", []) if q]
    return out


def subqueries(p, questions, n, writer, model, log, cancel):
    cands = [(q, "Gemini search") for q in gemini_searches(p)] + [(q, "buyer question") for q in questions]
    picked = []
    for q, origin in cands:
        if not any(_similar(q, x["query"]) for x in picked):
            picked.append({"query": q, "origin": origin})
    if len(picked) < n + 2 and writer:
        try:
            text = ai.chat(writer, model, "", FANOUT_PROMPT.format(topic=p["name"], n=n + 2),
                           temperature=0.2, json_mode=True, cancel=cancel, log=log)
            for q in ai.parse_json(text).get("searches", []) or []:
                q = str(q).strip()
                if q and not any(_similar(q, x["query"]) for x in picked):
                    picked.append({"query": q, "origin": "AI fan-out"})
        except ai.Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"  fan-out skipped ({str(e)[:80]})")
    return picked


# --- 3 + 4. writing and checking a section ----------------------------------------------------
def _strip_fence(t):
    return re.sub(r"\A```(?:markdown|md)?\s*\n(.*?)\n```\s*\Z", r"\1", t.strip(), flags=re.DOTALL)


def _cited(sentence):
    ids = []
    for m in CITE_RE.finditer(sentence):
        ids += [x.strip() for x in m.group(1).split(",")]
    return ids


def _sentences(md):
    """Factual sentences of a section (not headings), each with its [id]s."""
    out = []
    for line in md.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("-*> ").strip()
        for sent in re.split(r"(?<=[.!?\]])\s+(?=[A-Z])", s):
            if len(CITE_RE.sub("", sent).split()) >= 4:
                out.append(sent.strip())
    return out


def check_section(md, ev, writer, model, log, cancel):
    """Verdict per sentence against the evidence it cites. ev: {id: Unit}."""
    backend, label = verify.backend_name(writer, model)
    results, ask = [], []
    for sent in _sentences(md):
        claim = CITE_RE.sub("", sent).strip()
        ids = [i for i in _cited(sent) if i in ev]
        bad_ids = [i for i in _cited(sent) if i not in ev]
        units = [ev[i] for i in ids]
        r = {"sentence": sent, "claim": claim, "cites": ids, "bad_ids": bad_ids}
        if not units:
            r.update(verdict="unsupported", method="no citation",
                     note="cites an id that is not its evidence" if bad_ids else "no [id] citation")
            results.append(r)
            continue
        quick = verify.check_claim(claim, units, backend, label, writer, model, use_model=False)
        if quick["method"] in ("copied from a source", "numbers"):
            r.update(verdict=quick["verdict"], method=quick["method"], note=quick.get("note", ""))
        elif backend == "minicheck":
            verdict, _, note = verify._minicheck(label, "\n".join(u.text for u in units), claim)
            r.update(verdict=verdict, method="MiniCheck", note=note)
        else:
            ask.append(r)
        results.append(r)
    if ask:  # one call for the whole section
        listing = "\n".join(f"[{u.id}] {u.text}" for u in ev.values())
        claims = "\n".join(f"{k + 1}. {r['claim']}  (cites: {', '.join(r['cites'])})" for k, r in enumerate(ask))
        try:
            text = ai.chat(writer, model, BATCH_CHECK, f"EVIDENCE:\n{listing}\n\nCLAIMS:\n{claims}",
                           temperature=0.0, json_mode=True, cancel=cancel, log=log)
            verdicts = ai.parse_json(text).get("claims", {}) or {}
        except ai.Cancelled:
            raise
        except Exception:  # noqa: BLE001
            verdicts = {}
        for k, r in enumerate(ask):
            d = verdicts.get(str(k + 1)) or {}
            v = str(d.get("verdict", "unsupported")).lower()
            quote = str(d.get("quote", "") or "")
            cited_text = verify._norm(" ".join(ev[i].text for i in r["cites"]))
            if v in ("supported", "partly") and (not quote or verify._norm(quote) not in cited_text):
                v, note = "unsupported", "the checker could not quote the cited evidence"
            else:
                note = f'quote: "{quote[:120]}"' if quote else ""
            r.update(verdict=v if v in ("supported", "partly", "unsupported") else "unsupported",
                     method="AI check", note=note, quote=quote)
    return results


def _evidence_text(units):
    return "\n".join(f"[{u.id}] {u.text[:700]}" for u in units)


def _drop(md, sentences):
    for s in sentences:
        md = md.replace(s, "")
    md = re.sub(r"[ \t]{2,}", " ", md)
    lines = [l.rstrip() for l in md.splitlines() if not re.fullmatch(r"\s*[-*>]\s*", l)]  # emptied bullets
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _write_checked(prompt, ev_units, topic, writer, model, log, cancel, fresh, salt):
    ev = {u.id: u for u in ev_units}
    draft = _strip_fence(ai.chat(writer, model, "", prompt, temperature=0.3, cancel=cancel,
                                 use_cache=not fresh, log=log, salt=salt))
    checks = check_section(draft, ev, writer, model, log, cancel)
    bad = [c for c in checks if c["verdict"] == "unsupported"]
    final, rewritten = draft, False
    if bad:
        problems = "\n".join(f'- "{c["claim"]}" ({c.get("note") or c["method"]})' for c in bad)
        final = _strip_fence(ai.chat(writer, model, "", FIX_PROMPT.format(
            problems=problems, evidence=_evidence_text(ev_units), section=draft),
            temperature=0.2, cancel=cancel, use_cache=not fresh, log=log, salt=salt))
        rewritten = True
        checks = check_section(final, ev, writer, model, log, cancel)
    dropped = [c["sentence"] for c in checks if c["verdict"] == "unsupported"]
    final = _drop(final, dropped)
    return {"draft": draft, "rewritten": rewritten, "checks": checks, "dropped": dropped, "final": final}


# --- 5. the page ------------------------------------------------------------------------------
def clean(md):
    """The page without [id] citations, for publishing and the citation test."""
    md = CITE_RE.sub("", md)
    return re.sub(r"[ \t]+([.,;:])", r"\1", md)


def write_page(p, sheet, questions, s, log=print, cancel=None, step=None):
    """Returns (cited_md, clean_md, process). s: the run settings."""
    writer, model = s["writer"], s["writer_model"]
    fresh = bool(s.get("fresh_pages"))
    words = int(s.get("words", 400))
    n_sec = max(3, min(7, round((words - 60) / 90)))
    per_sec = max(60, (words - 60) // n_sec)
    reranker = (s.get("reranker") or writer, s.get("reranker_model") or model)
    use_emb = s.get("embeddings", True)
    emb_ok, emb_msg = retrieval.embed_status(s.get("embed_model") or retrieval.EMBED_MODEL) if use_emb else (False, "embeddings off")
    log(f"Section writer: {emb_msg}; reranker {reranker[0]} {reranker[1]}")

    units = evidence_units(p, sheet)
    if not units:
        raise ValueError("The fact sheet has no facts to write from.")
    log(f"  {len(units)} evidence units ({sum(u.id.startswith('w') for u in units)} wiki facts, "
        f"{sum(u.id.startswith('r') for u in units)} original passages)")
    guide = products.guidelines(p)
    guide = ("\nWriting guidelines of this product's wiki (follow them):\n" + guide[:2500] + "\n") if guide else ""

    cands = subqueries(p, questions, n_sec, writer, model, log, cancel)
    log(f"  {len(cands)} sub-queries: " + "; ".join(c["query"] for c in cands[:10]))
    sections, missing = [], []
    for i, c in enumerate(cands):
        if sum(not x["empty"] for x in sections) >= n_sec:
            c["kept"], c["why"] = False, "enough sections"
            continue
        if step:
            step("Writing the page section by section", sum(not x["empty"] for x in sections), n_sec)
        hits = retrieval.hybrid(c["query"], units, k=12, use_embeddings=emb_ok)
        top = retrieval.rerank(c["query"], hits, *reranker, top=5, log=log, cancel=cancel)
        graded = [h for h in top if h.get("grade") is not None]
        if (graded and max(h["grade"] for h in graded) < 2) or not top or top[0]["bm25"] == 0 and top[0]["cos"] is None:
            c["kept"], c["why"] = False, "no evidence answers it: a missing fact"
            missing.append(c["query"])
            log(f"  skipped (no evidence): {c['query']}")
            continue
        chosen = {h["unit"].id for h in top}
        c["kept"] = True
        ev_units = [h["unit"] for h in top]
        prompt = SECTION_PROMPT.format(topic=p["name"], query=c["query"], words=per_sec,
                                       guidelines=guide, evidence=_evidence_text(ev_units))
        log(f"  section {len(sections) + 1}: {c['query']} (evidence {', '.join(sorted(chosen))})")
        res = _write_checked(prompt, ev_units, p["name"], writer, model, log, cancel, fresh, f"sec{i}")
        sup = sum(x["verdict"] == "supported" for x in res["checks"])
        log(f"    {sup}/{len(res['checks'])} sentences supported"
            + (f", rewritten once" if res["rewritten"] else "")
            + (f", {len(res['dropped'])} removed" if res["dropped"] else ""))
        empty = not any(x["verdict"] in ("supported", "partly") for x in res["checks"]
                        if x["sentence"] not in res["dropped"])
        if empty:  # nothing the evidence supports: no section, a fact to find instead
            c["kept"], c["why"] = False, "every sentence failed the check: a missing fact"
            missing.append(c["query"])
            log("    section left out: no sentence is supported by its evidence")
        sections.append({"query": c["query"], "origin": c["origin"], "evidence": sorted(chosen), "empty": empty,
                         "candidates": [{**h["unit"].as_dict(240), **{k: h.get(k) for k in (
                             "bm25", "bm25_rank", "cos", "dense_rank", "rrf", "rrf_rank", "grade", "rerank_rank")},
                             "chosen": h["unit"].id in chosen} for h in hits], **res})

    page_secs = [x for x in sections if not x["empty"]]
    if not page_secs:
        raise ValueError("No sub-query had evidence in the wiki, so no section could be written.")
    hits = retrieval.hybrid(p["name"], units, k=10, use_embeddings=emb_ok)
    intro_units = [h["unit"] for h in hits[:5]]
    intro = _write_checked(INTRO_PROMPT.format(topic=p["name"], words=60, evidence=_evidence_text(intro_units)),
                           intro_units, p["name"], writer, model, log, cancel, fresh, "intro")
    cited_md = intro["final"] + "\n\n" + "\n\n".join(x["final"] for x in page_secs)
    allc = intro["checks"] + [c for x in page_secs for c in x["checks"]]
    final_claims = [c for c in allc if c["sentence"] not in intro["dropped"] + [d for x in page_secs for d in x["dropped"]]]
    with_cite = [c for c in final_claims if c["cites"]]
    metrics = {
        "sections": len(page_secs), "sentences": len(final_claims),
        "citation_coverage": round(len(with_cite) / len(final_claims), 3) if final_claims else None,
        "citation_precision": round(sum(c["verdict"] == "supported" for c in with_cite) / len(with_cite), 3) if with_cite else None,
        "removed": len(allc) - len(final_claims),
        "rewritten_sections": sum(x["rewritten"] for x in page_secs) + intro["rewritten"],
    }
    log(f"  page: {metrics['sections']} sections, citation precision {metrics['citation_precision']}, "
        f"coverage {metrics['citation_coverage']}, {metrics['removed']} sentence(s) removed")
    process = {"topic": p["name"], "embeddings": emb_msg, "reranker": f"{reranker[0]} {reranker[1]}",
               "writer": f"{writer} {model}", "units": len(units), "subqueries": cands,
               "missing": missing, "intro": intro, "sections": sections, "metrics": metrics,
               "unit_text": {u.id: {"source": u.source, "text": u.text[:400]} for u in units}}
    return cited_md, clean(cited_md), process


def unit_map(p, sheet, queries, extra=None, model=retrieval.EMBED_MODEL):
    """Points for the embedding map: wiki/raw evidence, sub-queries and (optional)
    other passages [(kind, label, text)]. Returns [{kind, id, label, text, x, y}]."""
    units = evidence_units(p, sheet)
    items = [("wiki" if u.id.startswith("w") else "raw", u.id, u.text) for u in units]
    items += [(k, lab_, t) for k, lab_, t in (extra or [])]
    vecs = retrieval.embed([t for _, _, t in items], model, "document")
    qvecs = retrieval.embed(queries, model, "query") if queries else []
    xy = retrieval.project_2d(vecs + qvecs)
    pts = [{"kind": k, "id": i, "text": t[:220], "x": x, "y": y}
           for (k, i, t), (x, y) in zip(items, xy[:len(items)])]
    pts += [{"kind": "query", "id": f"q{n + 1}", "text": q, "x": x, "y": y}
            for n, (q, (x, y)) in enumerate(zip(queries, xy[len(items):]))]
    return pts


def load_process(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
