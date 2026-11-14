"""
Fact check: is every claim on a page backed by a source?

A cascade, so the model only looks at what is in doubt (the 2026 practice for
grounding checks, e.g. FACTOR, VeriFastScore):

  1. Split the page into claims: sentences, list items, table rows (a row is
     read as "header: value; header: value").
  2. Copied?   A claim that appears (almost) word for word in a source is
               supported. Most of a page built from the wiki or from Danfoss's
               own text stops here, at no cost.
  3. Evidence. The 3 source passages that best match the claim (BM25) from:
               the wiki facts, the original documents in raw/, and the snapshots
               of Danfoss's pages copied in the Web page tab.
  4. Numbers.  Every number in the claim must appear in that evidence, or the
               claim fails: the cheapest check, and the most common invention.
  5. Model.    A grounding checker reads evidence + claim:
               - Bespoke-MiniCheck-7B if it is installed in Ollama
                 (`ollama pull bespoke-minicheck`): small, made for exactly this,
                 as accurate as GPT-4-class judges on LLM-AggreFact. Check its
                 licence before commercial use.
               - otherwise the AI chosen in the app, which must quote the exact
                 words of the evidence that support the claim. The quote is
                 checked in code: no quote found in the evidence = not supported.
                 That gives the span the old NLI checkers could not.

The verdict proves a claim is SUPPORTED by a source, not that the source is right.
"""
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "lab"))
import experiment as lab  # noqa: E402
import generate_variants as gv  # noqa: E402

import ai  # noqa: E402

NUM_RE = re.compile(r"\d[\d.,]*\d|\d")
MINICHECK = "bespoke-minicheck"

CHECK_SYSTEM = """You check whether a CLAIM is supported by the EVIDENCE.
Supported = everything the claim states is stated in the evidence (same meaning;
paraphrase is fine). Partly = some of it. Unsupported = the evidence does not say it,
or says something different. Use only the evidence, not your own knowledge.

Reply with JSON only:
{"verdict": "supported" | "partly" | "unsupported",
 "quote": "the exact words copied from the evidence that support the claim, or empty",
 "reason": "one short sentence"}"""


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w%.,-]+", " ", (s or "").lower())).strip()


def _numbers(s):
    return {re.sub(r"[.,]", "", n) for n in NUM_RE.findall(s or "")}


# --- evidence ------------------------------------------------------------------------
class _Unit:
    def __init__(self, source, text):
        self.source, self.text = source, text


def evidence_units(p):
    """Every source passage a claim may rest on: wiki facts (line by line, with
    their concept's title), raw/ documents and Danfoss page snapshots."""
    import products
    units = []
    try:
        sheet = gv.facts_only(products.fact_sheet(p))
    except ValueError:
        sheet = ""
    title = "wiki"
    for line in sheet.splitlines():
        s = line.strip()
        if s.startswith("## "):
            title = s[3:]
            continue
        s = s.lstrip("-*# ").strip()
        if len(s.split()) >= 3:
            units.append(_Unit(f"wiki: {title}", s))
    for sid, head, text in gv.raw_passages(REPO / p.get("raw_dir", "raw")):
        units.append(_Unit(f"raw: {sid}", (head + " " + text).strip()))
    site = p["folder"] / "webpage" / "site"
    if site.is_dir():
        for f in sorted(site.glob("*/original.md")):
            body = f.read_text(encoding="utf-8")
            m = lab.FRONT_RE.match(body)
            body = body[m.end():] if m else body
            for ps in lab.split_passages(body, 120):
                units.append(_Unit(f"danfoss.com: {f.parent.name}", ps["text"]))
    return units


# --- claims ------------------------------------------------------------------------
def claims(md):
    """Checkable claims of a page in Markdown."""
    out, table_head = [], None
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    for line in md.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or re.fullmatch(r"\|?\s*:?-{3,}.*", s):
            if not s.startswith("|"):
                table_head = None
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if table_head is None:
                table_head = cells
                continue
            out.append("; ".join(f"{h}: {c}" for h, c in zip(table_head, cells) if c))
            continue
        table_head = None
        s = re.sub(r"^([-*+]|\d+\.)\s+", "", s).replace("**", "")
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", s):
            if len(sent.split()) >= 4:
                out.append(sent.strip())
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


# --- the check -------------------------------------------------------------------------
def ollama_models():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def backend_name(provider, model):
    mc = next((m for m in ollama_models() if m.startswith(MINICHECK)), None)
    return ("minicheck", mc) if mc else ("llm", f"{provider}/{model}")


def _minicheck(model, evidence, claim):
    body = json.dumps({"model": model, "prompt": f"Document: {evidence}\nClaim: {claim}",
                       "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        ans = json.loads(r.read()).get("response", "").strip().lower()
    return ("supported" if ans.startswith("yes") else "unsupported"), "", "MiniCheck: " + (ans[:20] or "no answer")


def check_page(p, md, provider, model, log=lambda m: None, cancelled=lambda: False, max_model=60):
    """Verdicts for every claim of a page. Returns {summary, claims, backend}."""
    units = evidence_units(p)
    if not units:
        raise ValueError("No sources to check against (wiki, raw/ or Danfoss snapshots).")
    norm_units = [_norm(u.text) for u in units]
    bm25 = lab.BM25(units)
    backend, label = backend_name(provider, model)
    log(f"Checking against {len(units)} source passages; model step: {label}")
    results, model_calls = [], 0
    for n, c in enumerate(claims(md), 1):
        if cancelled():
            break
        nc = _norm(c)
        hit = next((i for i, u in enumerate(norm_units) if nc and nc in u), None)
        if hit is not None:
            results.append({"claim": c, "verdict": "supported", "method": "copied from a source",
                            "evidence": [{"source": units[hit].source, "text": units[hit].text[:300]}]})
            continue
        top = [u for s, u in bm25.rank(c)[:3] if s > 0]
        ev_text = "\n".join(u.text for u in top)
        evidence = [{"source": u.source, "text": u.text[:300]} for u in top]
        missing = sorted(_numbers(c) - _numbers(ev_text), key=len)
        if missing:
            results.append({"claim": c, "verdict": "unsupported", "method": "numbers",
                            "note": "number(s) not in the best-matching sources: " + ", ".join(missing),
                            "evidence": evidence})
            continue
        if not top:
            results.append({"claim": c, "verdict": "unsupported", "method": "no matching source", "evidence": []})
            continue
        if model_calls >= max_model:
            results.append({"claim": c, "verdict": "not checked", "method": "limit reached", "evidence": evidence})
            continue
        model_calls += 1
        log(f"  [{n}] model check: {c[:70]}")
        if backend == "minicheck":
            verdict, quote, note = _minicheck(label, ev_text, c)
        else:
            text = ai.chat(provider, model, CHECK_SYSTEM, f"EVIDENCE:\n{ev_text}\n\nCLAIM: {c}",
                           temperature=0.0, json_mode=True)
            try:
                d = ai.parse_json(text)
            except (ValueError, json.JSONDecodeError):
                d = {"verdict": "unsupported", "quote": "", "reason": "the checker's answer could not be read"}
            verdict = str(d.get("verdict", "unsupported")).lower()
            quote = str(d.get("quote", "") or "")
            note = str(d.get("reason", "") or "")
            if verdict in ("supported", "partly") and (not quote or _norm(quote) not in _norm(ev_text)):
                verdict, note = "unsupported", "the checker could not quote the evidence: " + note
        results.append({"claim": c, "verdict": verdict if verdict in ("supported", "partly", "unsupported") else "unsupported",
                        "method": "model", "quote": quote, "note": note, "evidence": evidence})
    counts = {k: sum(r["verdict"] == k for r in results) for k in ("supported", "partly", "unsupported", "not checked")}
    checked = counts["supported"] + counts["partly"] + counts["unsupported"]
    order = {"unsupported": 0, "partly": 1, "not checked": 2, "supported": 3}
    results.sort(key=lambda r: order.get(r["verdict"], 4))
    return {"backend": label, "summary": {**counts, "claims": len(results), "model_calls": model_calls,
                                          "supported_ratio": round(counts["supported"] / checked, 3) if checked else None},
            "claims": results}
