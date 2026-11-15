#!/usr/bin/env python3
"""
Atlas app: a small web app on your own computer that runs the whole process.

  python Run.py app          (or double-click "Start Atlas.bat")

It opens in your browser. Only you can reach it (it listens on 127.0.0.1 only).
"""
import base64
import http.server
import json
import mimetypes
import pathlib
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
STATIC = APP / "static"
sys.path.insert(0, str(APP))
import ai  # noqa: E402
import analysis  # noqa: E402
import brochure  # noqa: E402
import catalog  # noqa: E402
import citations  # noqa: E402
import comparison  # noqa: E402
import verify  # noqa: E402
import chat  # noqa: E402
import live  # noqa: E402
import pipeline  # noqa: E402
import products  # noqa: E402
import retrieval  # noqa: E402
import sections  # noqa: E402
import watch  # noqa: E402
import webpage  # noqa: E402
import website  # noqa: E402
import wikiedit  # noqa: E402


# --- the one background run -----------------------------------------------------
class Job:
    def __init__(self, slug, settings):
        self.slug, self.settings = slug, settings
        self.status, self.error, self.result = "running", None, None
        self.step_name, self.done, self.total = "Starting", 0, 0
        self.lines, self.stop, self.analysis_run = [], False, None
        self.started = time.time()

    def log(self, msg):
        self.lines.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        del self.lines[:-500]

    def step(self, name, done, total):
        if name != self.step_name:
            self.log(name + " ...")
        self.step_name, self.done, self.total = name, done, total

    def cancelled(self):
        return self.stop

    def as_dict(self):
        return {"slug": self.slug, "status": self.status, "error": self.error,
                "result": self.result, "step": self.step_name, "done": self.done,
                "total": self.total, "log": self.lines[-200:],
                "elapsed": int(time.time() - self.started)}


JOB = None
LOCK = threading.Lock()


def start_job(slug, settings, analysis_run=None):
    global JOB
    with LOCK:
        if JOB and JOB.status == "running":
            raise ValueError("A run is already going. Wait for it, or press Stop.")
        products.get(slug)
        JOB = Job(slug, settings)
        JOB.analysis_run = analysis_run
    threading.Thread(target=_run, args=(JOB,), daemon=True).start()


def _run(job):
    try:
        if job.analysis_run:  # only the wiki analysis of a finished run, again
            p = products.get(job.slug)
            out = run_folder(p, job.analysis_run)
            job.result = pipeline.run_analysis(job, p, out)
            if job.result["analysis"]["status"] == "error":
                raise RuntimeError(job.result["analysis"]["error"])
        else:
            job.result = pipeline.run(job, job.slug, job.settings)
        job.status = "done"
        job.log("Finished.")
    except ai.Cancelled:
        job.status = "cancelled"
        job.log("Stopped by you.")
    except (ValueError, RuntimeError) as e:
        job.status, job.error = "error", str(e)
        job.log("ERROR: " + str(e))
    except BaseException as e:  # noqa: BLE001  (SystemExit from the team's scripts too)
        job.status, job.error = "error", f"Unexpected problem: {e}"
        job.log(traceback.format_exc())


# --- data for the page ---------------------------------------------------------------
def deps():
    out = {}
    for mod in ("fpdf", "pypdf"):
        try:
            __import__(mod)
            out[mod] = True
        except ImportError:
            out[mod] = False
    return out


def state():
    ai.load_env()
    provs = {}
    for pid, p in ai.providers().items():
        info = {"label": p["label"], "models": p.get("models", []), "key_env": p.get("key_env"),
                "has_key": ai.has_key(p.get("key_env")), "base_url": p["base_url"],
                "sleep": p.get("sleep", 0), "type": p.get("type", "openai"),
                "est_write": p.get("est_write", 30), "est_answer": p.get("est_answer", 10)}
        if info["type"] == "ollama":
            info["reachable"], installed = ai.ollama_status(p["base_url"])
            # embedding models (e.g. nomic-embed-text, used by "Words + meaning") can't chat,
            # so they must never be offered as a writer, judge or brochure model
            installed = [m for m in installed if "embed" not in m.lower()]
            # show the models that are really installed on that server first
            info["installed"] = installed
            info["models"] = installed + [m for m in info["models"] if m not in installed]
        provs[pid] = info
    return {"products": products.list_products(), "providers": provs,
            "gemini_key": ai.has_key("GEMINI_API_KEY"), "standard": products.standard_questions(),
            "defaults": pipeline.DEFAULTS, "deps": deps(),
            "default_targets": analysis.default_targets(),
            "styles": [{"id": k, "name": pipeline.STYLE_NAMES.get(k, k),
                        "publishable": k in pipeline.PUBLISHABLE}
                       for k in [*pipeline.gv.STYLES, pipeline.SECTIONS]],
            "job": JOB.as_dict() if JOB else None, "watch": watch_brief()}


def watch_brief():
    try:
        st = watch.status()
    except Exception:  # noqa: BLE001
        return None
    unread = [a for a in st["alerts"] if not a["read"]]
    return {"unread": len(unread), "latest": unread[0]["title"] if unread else None,
            "kind": unread[0]["kind"] if unread else None}


def run_folder(p, run):
    if not run or "/" in run or "\\" in run or run.startswith("."):
        raise ValueError("Unknown run")
    out = p["folder"] / "runs" / run
    if not (out / "result.json").is_file():
        raise ValueError("Unknown run")
    return out


def product_info(slug):
    p = products.get(slug)
    try:
        sheet, sheet_error = products.fact_sheet(p), None
    except ValueError as e:
        sheet, sheet_error = "", str(e)
    pages = pipeline.load_pages(p, 50)
    runs = []
    runs_dir = p["folder"] / "runs"
    if runs_dir.is_dir():
        for d in sorted(runs_dir.iterdir(), reverse=True):
            if (d / "result.json").is_file():
                r = json.loads((d / "result.json").read_text(encoding="utf-8"))
                runs.append(r)
            elif d.is_dir():
                runs.append({"run": d.name, "unfinished": True})
    return {
        "product": {k: p.get(k, "") for k in ("slug", "name", "product_type", "application", "keyword")},
        "danfoss_url": danfoss_url(p),
        "questions": products.questions(p), "holdout": products.holdout(p),
        "fact_sheet": sheet, "fact_sheet_error": sheet_error,
        "pages": {"danfoss": sum(d.brand.lower() == "danfoss" for d in pages),
                  "competitors": sum(d.brand.lower() != "danfoss" for d in pages),
                  "fixed_links": len(products.source_list(p))},
        "runs": runs[:20],
        "targets": analysis.product_targets(p),
        # suggestions of the latest finished run, to accept or decline
        "suggestions": next((analysis.load(p["folder"] / "runs" / r["run"])
                             for r in runs if not r.get("unfinished")), None),
    }


def danfoss_url(p):
    """The product's current Danfoss page: the first Danfoss link of its fixed list."""
    return next((u for b, u in products.source_list(p) if b.lower() == "danfoss"), "")


def page_context(slug):
    """Product, ticked questions and competitor pages, for the Web page tabs."""
    p = products.get(slug)
    questions = [q["text"] for q in products.questions(p) if q["enabled"]]
    if not questions:
        raise ValueError("Tick at least one buyer question in the Run tab.")
    competitors = [d for d in pipeline.load_pages(p, pipeline.DEFAULTS["max_words"])
                   if d.brand.lower() != pipeline.TARGET]
    if not competitors:
        raise ValueError("No competitor pages saved yet: run once with 'Find fresh sources' on.")
    return p, questions, competitors


class SiteJob:
    """Copying a site section in the background (it takes a minute or two)."""

    def __init__(self, slug):
        self.slug, self.status, self.error, self.lines, self.stop = slug, "running", None, [], False
        self.started = time.time()

    def log(self, msg):
        self.lines.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        del self.lines[:-300]

    def as_dict(self):
        return {"slug": self.slug, "status": self.status, "error": self.error,
                "log": self.lines[-80:], "elapsed": int(time.time() - self.started)}


SITE_JOB = None


def site_state(slug):
    p = products.get(slug)
    if not (SITE_JOB and SITE_JOB.slug == slug and SITE_JOB.status == "running"):
        website.refresh(p, danfoss_url(p))  # the wiki may have changed: rebuild from it
    site = website.load_map(p)
    return {"site": site, "checks": website.site_checks(p) if site else None, "history": website.history(p),
            "lab_page": website.lab_page(p, danfoss_url(p)) if site else None,
            "start": website.default_start(p, danfoss_url(p)),
            "job": SITE_JOB.as_dict() if SITE_JOB and SITE_JOB.slug == slug else None}


def start_site_copy(b):
    global SITE_JOB
    p = products.get(b.get("slug", ""))
    url = (b.get("url") or website.default_start(p, danfoss_url(p))).strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Give the address of the Danfoss page or catalog to copy (https://...).")
    with LOCK:
        if SITE_JOB and SITE_JOB.status == "running":
            raise ValueError("A copy is already running. Wait for it, or press Stop.")
        SITE_JOB = job = SiteJob(p["slug"])

    def work():
        try:
            website.copy_site(p, url, also=[danfoss_url(p)], max_pages=max(1, min(int(b.get("max_pages") or 15), 40)),
                              replace=bool(b.get("replace")), log=job.log, cancelled=lambda: job.stop)
            # remember this website for the product, so the next update starts from it
            pj = p["folder"] / "product.json"
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("site_start") != url:
                data["site_start"] = url
                pj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            job.status = "done"
            job.log("Finished.")
        except (ValueError, RuntimeError) as e:
            job.status, job.error = "error", str(e)
            job.log("ERROR: " + str(e))
        except BaseException as e:  # noqa: BLE001
            job.status, job.error = "error", f"Unexpected problem: {e}"
            job.log(traceback.format_exc())
    threading.Thread(target=work, daemon=True).start()


def site_page(slug, pid):
    p, questions, competitors = page_context(slug)
    try:
        allowed = pipeline.gv.allowed_numbers(products.fact_sheet(p))
    except ValueError:
        allowed = frozenset()
    return website.page_analysis(p, pid, questions, competitors, allowed,
                                 website.lab_page(p, danfoss_url(p)))


def save_site_page(b):
    p = products.get(b.get("slug", ""))
    website.save_page(p, str(b.get("id", "")), str(b.get("text", "")))
    return {**site_page(p["slug"], str(b.get("id", ""))), "checks": website.site_checks(p)}


def import_site_page(b):
    p = products.get(b.get("slug", ""))
    raw = base64.b64decode(b.get("data", "")).decode("utf-8", errors="replace")
    pid = website.import_page(p, (b.get("url") or "").strip(), raw, b.get("filename", ""))
    return {"id": pid}


# --- Citations tab: the Gemini + Google Search agent -------------------------------------
CIT_JOB = None


def citations_state(slug):
    p = products.get(slug)
    runs = citations.list_runs()
    latest = runs[-1].name if runs else None
    ai.load_env()
    hist = citations.history()
    targets = analysis.product_targets(p)
    for r in hist["runs"]:  # the same targets as the Run tab, on Gemini's real answers
        r["targets"] = analysis.check({"trials": r["prompts"], "cited_count": r["danfoss_answers"],
                                       "first_count": r["danfoss_first"]}, targets)
    return {"history": hist, "targets": targets, "lab": citations.lab_history(p),
            "sections": {k: len(v) for k, v in citations.prompt_sections().items()},
            "latest": latest, "summary": citations.run_summary(latest) if latest else [],
            "ours": [{"id": o["id"], "label": o["label"]} for o in citations.our_pages(p, danfoss_url(p))],
            "has_key": ai.has_key("GEMINI_API_KEY"),
            "job": CIT_JOB.as_dict() if CIT_JOB else None}


def citations_prompt(q):
    p = products.get(q.get("slug", ""))
    rows = citations.load_run(q.get("run", ""))
    i = int(q.get("i", 0))
    if not 0 <= i < len(rows):
        raise ValueError("No such prompt in that run")
    row = rows[i]
    ours = next((o for o in citations.our_pages(p, danfoss_url(p)) if o["id"] == q.get("ours")), None) \
        or (citations.our_pages(p, danfoss_url(p)) or [None])[0]
    srcs = sorted(row["sources"], key=lambda s: -citations._share(s, row))
    return {"prompt": row["prompt"], "asked_at": row.get("asked_at", ""), "model": row.get("model", ""),
            "answer": row.get("answer", ""), "search_queries": row.get("search_queries", []),
            "coverage": round(row["supported_chars"] / row["answer_chars"], 3) if row.get("answer_chars") else None,
            "sources": [{"site": s.get("domain"), "url": s.get("url"), "share": citations._share(s, row),
                         "supports": s.get("supports", 0), "confidence": s.get("confidence"),
                         "rank": s.get("rank"), "danfoss": citations.is_target(s)} for s in srcs],
            "ours": {"id": ours["id"], "label": ours["label"]} if ours else None,
            "compare": citations.compare(row, ours) if ours else None}


def start_citations_update(b):
    global CIT_JOB
    sections = citations.prompt_sections()
    want = b.get("section") or "all"
    prompts = [x for v in sections.values() for x in v] if want == "all" else sections.get(want, [])
    limit = int(b.get("limit") or 0)
    if limit:
        prompts = prompts[:limit]
    if not prompts:
        raise ValueError("No prompts to ask.")
    with LOCK:
        if CIT_JOB and CIT_JOB.status == "running":
            raise ValueError("An update is already running.")
        CIT_JOB = job = SiteJob(b.get("slug", ""))
    all_prompts = want == "all" and not limit

    def work():
        try:
            job.log(f"Asking Gemini with Google Search: {len(prompts)} prompts ({want})")
            name = citations.update(prompts, b.get("model") or "gemini-2.5-flash", job.log, all_prompts)
            job.status = "done"
            job.log(f"Finished: {name}")
        except (ValueError, RuntimeError) as e:
            job.status, job.error = "error", str(e)
            job.log("ERROR: " + str(e))
        except BaseException as e:  # noqa: BLE001
            job.status, job.error = "error", f"Unexpected problem: {e}"
            job.log(traceback.format_exc())
    threading.Thread(target=work, daemon=True).start()


# --- fact check (verify.py) ----------------------------------------------------------------
VERIFY_JOB = None


def page_markdown(p, kind, ref):
    """The text of a page to check: a page of the mini website, or a product page."""
    if kind == "site":
        _, items = website._copy_items(p, ref)
        return webpage.to_markdown(items)
    path = (webpage.store_paths(p)["folder"] / ref).resolve()
    root = webpage.store_paths(p)["folder"].resolve()
    if root not in path.parents or path.suffix != ".html" or not path.is_file():
        raise ValueError("Build the product page first.")
    _, blocks = webpage.parse_page(path.read_text(encoding="utf-8"))
    return webpage.to_markdown(blocks)


def start_verify(b):
    global VERIFY_JOB
    p = products.get(b.get("slug", ""))
    md = page_markdown(p, b.get("kind", "site"), str(b.get("ref", "")))
    with LOCK:
        if VERIFY_JOB and VERIFY_JOB.status == "running":
            raise ValueError("A fact check is already running.")
        VERIFY_JOB = job = SiteJob(p["slug"])
    job.result, job.key = None, f"{b.get('kind')}:{b.get('ref')}"

    def work():
        try:
            job.result = verify.check_page(p, md, b.get("provider") or "gemini", b.get("model") or "gemini-2.5-flash",
                                           log=job.log, cancelled=lambda: job.stop)
            job.status = "done"
            job.log("Finished.")
        except (ValueError, RuntimeError) as e:
            job.status, job.error = "error", str(e)
            job.log("ERROR: " + str(e))
        except BaseException as e:  # noqa: BLE001
            job.status, job.error = "error", f"Unexpected problem: {e}"
            job.log(traceback.format_exc())
    threading.Thread(target=work, daemon=True).start()


def verify_state():
    if not VERIFY_JOB:
        return None
    return {**VERIFY_JOB.as_dict(), "key": VERIFY_JOB.key, "result": VERIFY_JOB.result}


def citations_explain(b):
    p = products.get(b.get("slug", ""))
    row = citations.load_run(b.get("run", ""))[int(b.get("i", 0))]
    ours = next((o for o in citations.our_pages(p, danfoss_url(p)) if o["id"] == b.get("ours")), None)
    if not ours:
        raise ValueError("Pick one of our pages to compare.")
    return citations.explain(row, ours, b.get("provider") or "gemini", b.get("model") or "gemini-2.5-flash",
                             fresh=bool(b.get("fresh")))


def citations_suggest(b):
    """Explanation (cached) -> wiki suggestions, accepted or declined like a run's."""
    p = products.get(b.get("slug", ""))
    ours = next((o for o in citations.our_pages(p, danfoss_url(p)) if o["id"] == b.get("ours")), None)
    if not ours:
        raise ValueError("Pick one of our pages to compare.")
    explanation = citations_explain({**b, "fresh": False})
    return citations.suggest(p, b.get("run", ""), int(b.get("i", 0)), ours, explanation,
                             b.get("provider") or "ollama", b.get("model") or "qwen3:8b")


def citations_decide(b):
    p = products.get(b.get("slug", ""))
    folder = citations.suggestion_folder(b.get("run", ""), int(b.get("i", 0)), b.get("ours", ""))
    return analysis.decide(p, folder, b.get("id"), b.get("decision"), b.get("text"))


# --- How it works tab: what the section writer did -------------------------------------------
def process_runs(p):
    runs = sorted((p["folder"] / "runs").glob("*/process.json"), reverse=True)
    return [r.parent.name for r in runs]


def process_state(slug, run=""):
    p = products.get(slug)
    runs = process_runs(p)
    run = run if run in runs else (runs[0] if runs else "")
    proc = sections.load_process(p["folder"] / "runs" / run / "process.json") if run else None
    return {"runs": runs, "run": run, "process": proc,
            "has_map": bool(run) and (p["folder"] / "runs" / run / "process_map.json").is_file()}


def process_map(b):
    """2-D map of the embeddings: evidence, sub-queries, competitor passages and our sections."""
    p = products.get(b.get("slug", ""))
    run = b.get("run", "")
    if run not in process_runs(p):
        raise ValueError("No section-writer run to draw.")
    folder = p["folder"] / "runs" / run
    cache = folder / "process_map.json"
    if cache.is_file() and not b.get("fresh"):
        return json.loads(cache.read_text(encoding="utf-8"))
    ok, msg = retrieval.embed_status()
    if not ok:
        raise ValueError(msg)
    proc = sections.load_process(folder / "process.json")
    queries = [c["query"] for c in proc["subqueries"]]
    extra = [("ours", f"S{k + 1}", sections.clean(s["final"])) for k, s in enumerate(proc["sections"])
             if not s.get("empty") and s["final"].strip()]
    comps = [d for d in pipeline.load_pages(p, 2000) if d.brand.lower() != "danfoss"]
    if comps:  # the competitor passages that best match the sub-queries
        ranker = pipeline.lab.PassageRanker(comps, 120)
        seen = set()
        for q in queries:  # the 4 best competitor passages per sub-query
            for s, ps in ranker.scores(q)[:4]:
                if s > 0 and id(ps) not in seen:
                    seen.add(id(ps))
                    extra.append(("competitor", ps.doc.brand, (ps.heading + ": " + ps.body)[:1200]))
    sheet = products.fact_sheet(p)
    data = {"points": sections.unit_map(p, sheet, queries, extra), "queries": queries,
            "chosen": {f"q{k + 1}": next((s["evidence"] for s in proc["sections"] if s["query"] == q), [])
                       for k, q in enumerate(queries)}}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def build_product_page(b):
    p, questions, competitors = page_context(b.get("slug", ""))
    version = "ai" if b.get("version") == "ai" else "template"
    return catalog.build(p, str(b.get("id", "")), questions, competitors, version,
                         b.get("provider") or "gemini", b.get("model") or "gemini-2.5-flash",
                         fresh=bool(b.get("fresh")))


# --- Run › Results: the details of one run ---------------------------------------------------
def _jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.is_file() else []


def _vkey(r):
    return r.get("version") or r["style"]


def _vname(v, names):
    if v in names:
        return names[v]
    st, _, k = v.rpartition("_")
    return pipeline.version_name(st, int(k)) if st in pipeline.STYLE_NAMES and k.isdigit() else pipeline.STYLE_NAMES.get(v, v)


def run_detail(slug, run):
    """Per version and question: how often it was cited (the heatmap); the written versions."""
    p = products.get(slug)
    out = run_folder(p, run)
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    names = {x["version"]: x["name"] for x in res.get("ranking") or []}

    def grid(rows):
        if not rows:
            return None
        qs = list(dict.fromkeys(r["question"] for r in rows))
        order = [x["version"] for x in res.get("ranking") or []]
        versions = order + [v for v in dict.fromkeys(_vkey(r) for r in rows) if v not in order]
        cells = {}
        for r in rows:
            c = cells.setdefault(f"{_vkey(r)}|{qs.index(r['question'])}", {"n": 0, "cited": 0, "first": 0, "shown": 0})
            c["n"] += 1
            c["cited"] += bool(r["cited"])
            c["first"] += bool(r["first"])
            c["shown"] += bool(r["in_context"])
        present = {_vkey(r) for r in rows}
        return {"questions": qs, "cells": cells,
                "versions": [{"version": v, "name": _vname(v, names)} for v in versions if v in present]}
    try:
        sheet = products.fact_sheet(p)
    except ValueError:
        sheet = ""
    variants = []
    for f in sorted((out / "variants").glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        st, _, k = f.stem.rpartition("_")
        style = st if k.isdigit() and st in pipeline.STYLE_NAMES else f.stem
        variants.append({"version": f.stem, "name": _vname(f.stem, names), "file": f"variants/{f.name}",
                         "words": len(text.split()),
                         "unknown_numbers": sorted(pipeline.gv.norm_numbers(text) - pipeline.gv.allowed_numbers(sheet, style), key=len)
                         if sheet else []})
    return {"run": run, "main": grid(_jsonl(out / "citation_test.jsonl")),
            "holdout": grid(_jsonl(out / "citation_holdout.jsonl")), "variants": variants}


def run_answers(q):
    """JEV's real answers for one version and one question of a run."""
    p = products.get(q.get("slug", ""))
    out = run_folder(p, q.get("run", ""))
    rows = _jsonl(out / ("citation_holdout.jsonl" if q.get("holdout") == "1" else "citation_test.jsonl"))
    qs = list(dict.fromkeys(r["question"] for r in rows))
    i = int(q.get("i", 0))
    if not 0 <= i < len(qs):
        raise ValueError("No such question in that run")
    pick = [r for r in rows if _vkey(r) == q.get("version") and r["question"] == qs[i]]
    return {"question": qs[i], "answers": [{k: r.get(k) for k in (
        "repeat", "answer", "recommendation", "cited", "first", "in_context", "forced", "bm25_rank",
        "cited_brands", "labels")} for r in pick]}


# --- Wiki tab --------------------------------------------------------------------------------
RAW_JOB = None


def wiki_state(slug):
    p = products.get(slug)
    return {**wikiedit.files(p), "log": wikiedit.log_text(p), "raw": wikiedit.raw_status(p),
            "raw_job": RAW_JOB.as_dict() if RAW_JOB and RAW_JOB.slug == slug else None}


def wiki_save(b):
    p = products.get(b.get("slug", ""))
    r = wikiedit.save(p, str(b.get("path", "")), str(b.get("text", "")), str(b.get("note", "")), bool(b.get("create")))
    if r["changed"]:
        try:  # pages with {{wiki: ...}} blocks follow the wiki
            website.refresh(p, danfoss_url(p))
        except Exception as e:  # noqa: BLE001
            r["site_error"] = str(e)
    return {**r, **wiki_state(p["slug"])}


def start_raw_update(b):
    global RAW_JOB
    p = products.get(b.get("slug", ""))
    with LOCK:
        if RAW_JOB and RAW_JOB.status == "running":
            raise ValueError("The documents are already being downloaded.")
        RAW_JOB = job = SiteJob(p["slug"])

    def work():
        try:
            job.log("Downloading the documents the wiki cites…")
            wikiedit.update_raw(p, job.log)
            job.status = "done"
            job.log("Finished.")
        except BaseException as e:  # noqa: BLE001  (SystemExit from the lab script too)
            job.status, job.error = "error", str(e) or type(e).__name__
            job.log("ERROR: " + job.error)
    threading.Thread(target=work, daemon=True).start()


def site_zip(p):
    """The mini website as files to hand over: every page, sitemap.xml, robots.txt."""
    import io
    import zipfile
    paths = website.paths(p)
    if not website.load_map(p):
        raise ValueError("Load the pages first (Web page › Site › Pages to edit).")
    website.refresh(p, danfoss_url(p))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(paths["site"].glob("*.html")):
            z.write(f, f.name)
        if paths["sitemap"].is_file():
            z.write(paths["sitemap"], "sitemap.xml")
        z.writestr("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: https://www.danfoss.com/sitemap.xml\n")
        z.writestr("README.txt", "A section of danfoss.com as edited in Atlas for crawlers and AI search.\n"
                   "Every page is static HTML with its structured data (JSON-LD) in the <head>.\n"
                   "Product facts come from the Atlas wiki. sitemap.xml lists the pages with their real addresses.\n")
    return buf.getvalue()


def update_product(slug, fields):
    p = products.get(slug)
    path = p["folder"] / "product.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for k in ("product_type", "application", "keyword"):
        if k in fields:
            data[k] = str(fields[k]).strip()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- HTTP ------------------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal quiet
        pass

    def send(self, code, body, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # --- only Atlas's own page may talk to Atlas -------------------------------------------
    # Another website open in the browser could otherwise send requests to 127.0.0.1 (for
    # example change the Gemini address so the key goes elsewhere). The Host check stops
    # DNS rebinding; the Origin check stops cross-site requests; requiring JSON on POST stops
    # plain HTML forms, which cannot send it to another site without the browser asking first.
    def _hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def trusted(self, post):
        if (self.headers.get("Host") or "") not in self._hosts():
            return "Unknown host"
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).netloc not in self._hosts():
            return "Requests from other websites are not allowed"
        if post and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return "Send JSON"
        return None

    def do_GET(self):
        why = self.trusted(post=False)
        if why:
            return self.send(403, {"error": why})
        url = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path in ("/", "/index.html"):
                return self.static("index.html")
            if url.path.startswith("/static/"):
                return self.static(url.path[len("/static/"):])
            if url.path == "/live":  # the live danfoss.com page for the Web page tab
                try:
                    body = live.page(q.get("url", ""))
                except Exception as e:  # noqa: BLE001  (shown inside the frame)
                    body = live.error_page(q.get("url", ""), e)
                return self.send(200, body.encode("utf-8"), "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self.send(200, state())
            if url.path == "/api/product":
                return self.send(200, product_info(q.get("slug", "")))
            if url.path == "/api/pages":
                p = products.get(q.get("slug", ""))
                return self.send(200, {**comparison.status(p), **comparison.boxes(p),
                                       "google": comparison.google_link(p)})
            if url.path == "/api/import/status":
                return self.send(200, brochure.status())
            if url.path == "/api/job":
                return self.send(200, JOB.as_dict() if JOB else None)
            if url.path.startswith("/files/"):
                return self.file(urllib.parse.unquote(url.path[len("/files/"):]), q.get("download") == "1")
            if url.path == "/api/site":
                return self.send(200, site_state(q.get("slug", "")))
            if url.path == "/api/site/page":
                return self.send(200, site_page(q.get("slug", ""), q.get("id", "")))
            if url.path == "/api/site/original":  # before/after slider: the snapshot as a page
                html_page = website.render_original(products.get(q.get("slug", "")), q.get("id", ""))
                return self.send(200, html_page.encode("utf-8"), "text/html; charset=utf-8")
            if url.path == "/api/site/export":
                p = products.get(q.get("slug", ""))
                return self.send(200, site_zip(p), "application/zip",
                                 {"Content-Disposition": f'attachment; filename="{p["slug"]}_website.zip"'})
            if url.path == "/api/run/detail":
                return self.send(200, run_detail(q.get("slug", ""), q.get("run", "")))
            if url.path == "/api/run/answers":
                return self.send(200, run_answers(q))
            if url.path == "/api/wiki":
                return self.send(200, wiki_state(q.get("slug", "")))
            if url.path == "/api/wiki/file":
                return self.send(200, wikiedit.read(products.get(q.get("slug", "")), q.get("path", "")))
            if url.path == "/api/watch":
                return self.send(200, watch.status())
            if url.path == "/api/site/wiki":
                return self.send(200, website.wiki_blocks(products.get(q.get("slug", ""))))
            if url.path == "/api/citations":
                return self.send(200, citations_state(q.get("slug", "")))
            if url.path == "/api/citations/run":
                return self.send(200, citations.run_summary(q.get("run", "")))
            if url.path == "/api/citations/prompt":
                return self.send(200, citations_prompt(q))
            if url.path == "/api/citations/suggestions":
                return self.send(200, citations.load_suggestions(q.get("run", ""), int(q.get("i", 0)), q.get("ours", "")))
            if url.path == "/api/process":
                return self.send(200, process_state(q.get("slug", ""), q.get("run", "")))
            if url.path == "/api/chat/status":
                return self.send(200, chat.status())
            if url.path == "/api/chat/poll":
                return self.send(200, chat.poll(q.get("id", "")))
            if url.path == "/api/verify/job":
                return self.send(200, verify_state())
            if url.path == "/api/catalog":
                return self.send(200, catalog.catalog(products.get(q.get("slug", ""))))
            if url.path.startswith("/pages/"):
                return self.page(urllib.parse.unquote(url.path[len("/pages/"):]), q.get("download") == "1")
            self.send(404, {"error": "Not found"})
        except (ValueError, RuntimeError) as e:
            self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.send(500, {"error": f"Unexpected problem: {e}"})

    def do_POST(self):
        why = self.trusted(post=True)
        if why:
            return self.send(403, {"error": why})
        path = urllib.parse.urlsplit(self.path).path
        try:
            b = self.body()
            if path == "/api/run":
                start_job(b["slug"], b.get("settings", {}))
            elif path == "/api/stop":
                if JOB:
                    JOB.stop = True
            elif path == "/api/questions/select":
                products.set_enabled(products.get(b["slug"]), b.get("enabled", []))
            elif path == "/api/questions/add":
                if b.get("scope") == "standard":
                    products.add_standard(b.get("text", ""))
                elif b.get("scope") == "holdout":
                    products.add_holdout(products.get(b["slug"]), b.get("text", ""))
                else:
                    products.add_custom(products.get(b["slug"]), b.get("text", ""))
            elif path == "/api/questions/delete":
                if b.get("kind") == "standard":
                    products.delete_standard(b["id"])
                elif b.get("kind") == "holdout":
                    products.delete_holdout(products.get(b["slug"]), b["id"])
                else:
                    products.delete_custom(products.get(b["slug"]), b["id"])
            elif path == "/api/wiki/save":
                return self.send(200, wiki_save(b))
            elif path == "/api/raw/update":
                start_raw_update(b)
            elif path == "/api/watch/check":
                new = watch.check()
                return self.send(200, {"new": len(new), **watch.status()})
            elif path == "/api/watch/read":
                watch.mark_read()
            elif path == "/api/watch/test":
                return self.send(200, {"result": watch.test_email()})
            elif path == "/api/product/update":
                update_product(b["slug"], b)
            elif path == "/api/key":
                ai.save_key(b["env"], b.get("value", ""))
            elif path == "/api/provider/add":
                pid = ai.add_provider(b.get("id") or b.get("label", ""), b.get("label", ""),
                                      b.get("base_url", ""), b.get("key_env"),
                                      str(b.get("models", "")).split(","), b.get("sleep", 0))
                if b.get("key") and b.get("key_env"):
                    ai.save_key(b["key_env"].strip(), b["key"])
                return self.send(200, {"ok": True, "id": pid})
            elif path == "/api/provider/update":
                ai.update_provider(b["id"], base_url=b.get("base_url"))
            elif path == "/api/provider/remove":
                ai.remove_provider(b["id"])
            elif path == "/api/pages/save":
                p = products.get(b.get("slug", ""))
                comparison.save(p, b.get("danfoss", ""), b.get("competitors", ""))
                comparison.start_fetch(p)
            elif path == "/api/pages/retry":
                comparison.start_fetch(products.get(b.get("slug", "")))
            elif path == "/api/targets/default":
                analysis.set_default_targets(b)
            elif path == "/api/targets/product":
                analysis.set_product_targets(products.get(b.get("slug", "")), b, bool(b.get("reset")))
            elif path == "/api/suggestion":
                p = products.get(b.get("slug", ""))
                return self.send(200, analysis.decide(p, run_folder(p, b.get("run")), b.get("id"),
                                                      b.get("decision"), b.get("text")))
            elif path == "/api/analysis/run":
                p = products.get(b.get("slug", ""))
                run_folder(p, b.get("run"))
                start_job(p["slug"], {}, analysis_run=b["run"])
            elif path == "/api/import/start":
                # runs in the background: the page follows it with /api/import/status
                brochure.start(b["filename"], base64.b64decode(b["data"]),
                               b.get("provider") or "ollama", b.get("model") or "qwen3:8b")
            elif path == "/api/import/stop":
                brochure.stop()
            elif path == "/api/import/clear":
                brochure.clear()
            elif path == "/api/import/save":
                slug = products.create_product(b.get("draft", {}))
                brochure.clear()
                return self.send(200, {"slug": slug})
            elif path == "/api/catalog/build":
                return self.send(200, build_product_page(b))
            elif path == "/api/site/copy":
                start_site_copy(b)
            elif path == "/api/site/stop":
                if SITE_JOB:
                    SITE_JOB.stop = True
            elif path == "/api/site/save":
                return self.send(200, save_site_page(b))
            elif path == "/api/site/import":
                return self.send(200, import_site_page(b))
            elif path == "/api/citations/update":
                start_citations_update(b)
            elif path == "/api/citations/explain":
                return self.send(200, citations_explain(b))
            elif path == "/api/citations/suggest":
                return self.send(200, citations_suggest(b))
            elif path == "/api/citations/suggestion":
                return self.send(200, citations_decide(b))
            elif path == "/api/process/map":
                return self.send(200, process_map(b))
            elif path == "/api/chat":
                return self.send(200, chat.start(b.get("messages") or [], b.get("slug", ""), b.get("tab", ""),
                                                 b.get("model", "")))
            elif path == "/api/chat/stop":
                chat.stop(b.get("id", ""))
            elif path == "/api/verify":
                start_verify(b)
            elif path == "/api/verify/stop":
                if VERIFY_JOB:
                    VERIFY_JOB.stop = True
            else:
                return self.send(404, {"error": "Not found"})
            self.send(200, {"ok": True})
        except (ValueError, RuntimeError, KeyError) as e:
            self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.send(500, {"error": f"Unexpected problem: {e}"})

    def static(self, name):
        path = (STATIC / name).resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            return self.send(404, {"error": "Not found"})
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send(200, path.read_bytes(), ctype)

    def page(self, rel, download):
        """Generated web pages: /pages/<product>/<file under its webpage/ folder>.
        The downloaded original (cache/) is not served."""
        slug, _, name = rel.partition("/")
        root = webpage.store_paths(products.get(slug))["folder"].resolve()
        path = (root / name).resolve()
        types = {".html": "text/html", ".xml": "application/xml", ".md": "text/plain"}
        if (root not in path.parents or path.suffix not in types or not path.is_file()
                or "cache" in path.relative_to(root).parts):
            return self.send(404, {"error": "Page not found"})
        disp = ("attachment" if download else "inline") + f'; filename="{slug}_{path.name}"'
        self.send(200, path.read_bytes(), types[path.suffix] + "; charset=utf-8",
                  {"Content-Disposition": disp})

    def file(self, rel, download):
        """Files of a run: /files/<product>/<run>/<file>. Nothing outside products/runs."""
        path = (products.PRODUCTS / rel).resolve()
        root = products.PRODUCTS.resolve()
        if root not in path.parents or "runs" not in path.relative_to(root).parts or not path.is_file():
            return self.send(404, {"error": "File not found"})
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in (".md", ".csv", ".jsonl", ".json"):
            ctype = "text/plain; charset=utf-8"
        parts = path.relative_to(root).parts
        nice = f"{parts[0]}_{parts[2]}_{path.name}" if len(parts) >= 3 else path.name
        disp = ("attachment" if download else "inline") + f'; filename="{nice}"'
        self.send(200, path.read_bytes(), ctype, {"Content-Disposition": disp})


def start_watch():
    """News watch every WATCH_HOURS; Citations refresh every CITATIONS_EVERY_DAYS (0 = off)."""
    import datetime

    def last_citations():
        runs = citations.list_runs()
        return datetime.datetime.fromtimestamp(runs[-1].stat().st_mtime) if runs else None

    def refresh_citations():
        if ai.has_key("GEMINI_API_KEY") and not (CIT_JOB and CIT_JOB.status == "running"):
            start_citations_update({"section": "all"})
    watch.start_scheduler(refresh_citations, last_citations)


def free_port(start=8765):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("No free port found")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    ai.load_env()
    port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Atlas is running at {url}\nKeep this window open while you use it. Close it to stop.")
    start_watch()
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
