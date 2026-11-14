"""
Hybrid retrieval: BM25 + embeddings, fused with RRF, then a reranker.

The 2026 standard for finding the right evidence passage (two-stage hybrid
retrieval with reranking beat 9 other strategies on 23,088 queries):

  1. BM25        exact words. Good at model names, units, figures ("HP5", "10 bar").
  2. Embeddings  meaning. Finds "how efficient is it" in a passage that says
                 "COP" without sharing a word. Ollama's /api/embed, model
                 nomic-embed-text by default (`ollama pull nomic-embed-text`).
  3. RRF         Reciprocal Rank Fusion: score = sum of 1 / (60 + rank) over both
                 lists. Uses ranks, not raw scores, so the two scales never need
                 to be compared.
  4. Reranker    reads the query with each of the top candidates and grades how
                 well the passage answers it (0-3). Ollama has no cross-encoder
                 endpoint, so the reranker is a chat model asked for JSON grades,
                 all candidates in one call.

Every step degrades gracefully: no embedding model = BM25 only; no reranker =
the RRF order. Each result keeps its rank in every step, so the app can show
how a passage moved (the "how it works" view).

Embeddings are cached in app/cache/embeddings/ (not committed).
"""
import hashlib
import json
import math
import pathlib
import sys
import urllib.request

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO / "lab"))
import experiment as lab  # noqa: E402

import ai  # noqa: E402

EMBED_MODEL = "nomic-embed-text"
CACHE = APP / "cache" / "embeddings"
RRF_K = 60
_MEM = {}  # model -> {sha: vector}, loaded once per process


class Unit:
    """One piece of evidence: an id the writer cites ([w3], [r12]), where it comes
    from, and its text."""

    def __init__(self, uid, source, text):
        self.id, self.source, self.text = uid, source, text

    def as_dict(self, n=300):
        return {"id": self.id, "source": self.source, "text": self.text[:n]}


# --- embeddings ---------------------------------------------------------------------
def ollama_base():
    p = ai.providers().get("ollama") or {}
    return (p.get("base_url") or "http://localhost:11434/").rstrip("/")


def embed_status(model=EMBED_MODEL):
    """(ready, message) for the embedding model on the team's Ollama server."""
    reachable, installed = ai.ollama_status(ollama_base())
    if not reachable:
        return False, f"Ollama at {ollama_base()} is not reachable: using BM25 only."
    if not any(m == model or m.startswith(model + ":") for m in installed):
        return False, (f"Embedding model '{model}' is not installed on {ollama_base()}: using BM25 only. "
                       f"On that computer run:  ollama pull {model}")
    return True, f"embeddings: {model}"


def _prefix(model, text, kind):
    # nomic-embed-text was trained with task prefixes; other models ignore them
    if model.startswith("nomic-embed"):
        return ("search_query: " if kind == "query" else "search_document: ") + text
    return text


def _cache(model):
    if model not in _MEM:
        f = CACHE / (model.replace(":", "_").replace("/", "_") + ".json")
        try:
            _MEM[model] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _MEM[model] = {}
    return _MEM[model]


def _save(model):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (model.replace(":", "_").replace("/", "_") + ".json")
    f.write_text(json.dumps(_MEM.get(model, {})), encoding="utf-8")


def embed(texts, model=EMBED_MODEL, kind="document"):
    """One vector per text (normalised), from cache or Ollama. Raises if Ollama fails."""
    cache = _cache(model)
    keys = [hashlib.sha1(_prefix(model, t, kind).encode()).hexdigest() for t in texts]
    todo = [(k, _prefix(model, t, kind)) for k, t in zip(keys, texts) if k not in cache]
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        body = json.dumps({"model": model, "input": [t for _, t in batch]}).encode()
        req = urllib.request.Request(ollama_base() + "/api/embed", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            vecs = json.loads(r.read())["embeddings"]
        for (k, _), v in zip(batch, vecs):
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            cache[k] = [round(x / norm, 5) for x in v]
    if todo:
        _save(model)
    return [cache[k] for k in keys]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))  # vectors are normalised


# --- hybrid search ------------------------------------------------------------------------
def hybrid(query, units, k=20, model=EMBED_MODEL, use_embeddings=True):
    """Candidates for `query`: [{unit, bm25, bm25_rank, cos, dense_rank, rrf, rrf_rank}],
    best first. dense_* are None when embeddings are off or unavailable."""
    if not units:
        return []
    bm = lab.BM25(units)
    bm_ranked = bm.rank(query)
    bm_rank = {id(u): (i + 1, s) for i, (s, u) in enumerate(bm_ranked)}
    dense_rank = {}
    if use_embeddings:
        try:
            qv = embed([query], model, "query")[0]
            dv = embed([u.text for u in units], model, "document")
            sims = sorted(((cosine(qv, v), u) for v, u in zip(dv, units)), key=lambda x: -x[0])
            dense_rank = {id(u): (i + 1, s) for i, (s, u) in enumerate(sims)}
        except Exception:  # noqa: BLE001  (no model / server off: BM25 only)
            dense_rank = {}
    rows = []
    for u in units:
        br, bs = bm_rank[id(u)]
        rrf = (1 / (RRF_K + br)) if bs > 0 else 0.0
        dr, ds = dense_rank.get(id(u), (None, None))
        if dr is not None:
            rrf += 1 / (RRF_K + dr)
        rows.append({"unit": u, "bm25": round(bs, 3), "bm25_rank": br,
                     "cos": None if ds is None else round(ds, 4), "dense_rank": dr, "rrf": rrf})
    rows.sort(key=lambda r: -r["rrf"])
    for i, r in enumerate(rows):
        r["rrf_rank"] = i + 1
        r["rrf"] = round(r["rrf"], 5)
    return rows[:k]


RERANK_SYSTEM = """You grade how well each PASSAGE answers a search QUERY.
3 = answers it directly with specifics; 2 = clearly relevant, partial answer;
1 = same topic, does not answer; 0 = unrelated.
Judge the content only, not the length or formatting.
Reply with JSON only: {"grades": {"<passage number>": <0-3>, ...}}"""


def rerank(query, cands, provider, model, top=6, log=lambda m: None, cancel=None):
    """Re-order the candidates by a reranker's grade (ties keep the RRF order).
    Adds 'grade' and 'rerank_rank' to each row; returns the top ones."""
    if not cands:
        return []
    if provider:
        listing = "\n\n".join(f"[{i + 1}] {c['unit'].text[:600]}" for i, c in enumerate(cands))
        try:
            text = ai.chat(provider, model, RERANK_SYSTEM, f"QUERY: {query}\n\nPASSAGES:\n{listing}",
                           temperature=0.0, json_mode=True, cancel=cancel, log=log)
            grades = (ai.parse_json(text).get("grades") or {})
            for i, c in enumerate(cands):
                g = grades.get(str(i + 1), grades.get(i + 1))
                c["grade"] = max(0, min(3, int(g))) if isinstance(g, (int, float, str)) and str(g).strip().lstrip("-").isdigit() else None
        except ai.Cancelled:
            raise
        except Exception as e:  # noqa: BLE001  (a reranker problem must not stop the page)
            log(f"    reranker skipped ({str(e)[:80]})")
            for c in cands:
                c["grade"] = None
    else:
        for c in cands:
            c["grade"] = None
    order = sorted(cands, key=lambda c: (-(c["grade"] if c["grade"] is not None else -1), c["rrf_rank"]))
    for i, c in enumerate(order):
        c["rerank_rank"] = i + 1
    return [c for c in order if c["grade"] is None or c["grade"] >= 2][:top] or order[:min(2, top)]


# --- a 2-D map of the vectors (for the "how it works" view) ------------------------------------
def project_2d(vectors, iters=60):
    """PCA to two dimensions with power iteration (standard library only)."""
    n = len(vectors)
    if n < 3:
        return [(0.0, 0.0)] * n
    dim = len(vectors[0])
    mean = [sum(v[j] for v in vectors) / n for j in range(dim)]
    X = [[v[j] - mean[j] for j in range(dim)] for v in vectors]
    comps = []
    for c in range(2):
        w = [math.sin(1.7 * (j + 1) * (c + 1)) for j in range(dim)]
        for _ in range(iters):
            proj = [sum(a * b for a, b in zip(x, w)) for x in X]
            w = [sum(proj[i] * X[i][j] for i in range(n)) for j in range(dim)]
            for prev in comps:  # keep the components orthogonal
                d = sum(a * b for a, b in zip(w, prev))
                w = [a - d * b for a, b in zip(w, prev)]
            norm = math.sqrt(sum(a * a for a in w)) or 1.0
            w = [a / norm for a in w]
        comps.append(w)
    return [tuple(round(sum(a * b for a, b in zip(x, w)), 5) for w in comps) for x in X]
