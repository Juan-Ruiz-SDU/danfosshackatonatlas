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
import catalog  # noqa: E402
import citations  # noqa: E402
import verify  # noqa: E402
import pipeline  # noqa: E402
import products  # noqa: E402
import webpage  # noqa: E402
import website  # noqa: E402


# --- the one background run -----------------------------------------------------
class Job:
    def __init__(self, slug, settings):
        self.slug, self.settings = slug, settings
        self.status, self.error, self.result = "running", None, None
        self.step_name, self.done, self.total = "Starting", 0, 0
        self.lines, self.stop = [], False
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


def start_job(slug, settings):
    global JOB
    with LOCK:
        if JOB and JOB.status == "running":
            raise ValueError("A run is already going. Wait for it, or press Stop.")
        products.get(slug)
        JOB = Job(slug, settings)
    threading.Thread(target=_run, args=(JOB,), daemon=True).start()


def _run(job):
    try:
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
    provs = {pid: {"label": p["label"], "models": p.get("models", []), "key_env": p.get("key_env"),
                   "has_key": ai.has_key(p.get("key_env")), "base_url": p["base_url"],
                   "sleep": p.get("sleep", 0)}
             for pid, p in ai.providers().items()}
    return {"products": products.list_products(), "providers": provs,
            "gemini_key": ai.has_key("GEMINI_API_KEY"), "standard": products.standard_questions(),
            "defaults": pipeline.DEFAULTS, "deps": deps(),
            "styles": [{"id": k, "name": pipeline.STYLE_NAMES.get(k, k),
                        "publishable": k in pipeline.PUBLISHABLE}
                       for k in pipeline.gv.STYLES],
            "job": JOB.as_dict() if JOB else None}


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
        "questions": products.questions(p), "fact_sheet": sheet, "fact_sheet_error": sheet_error,
        "pages": {"danfoss": sum(d.brand.lower() == "danfoss" for d in pages),
                  "competitors": sum(d.brand.lower() != "danfoss" for d in pages),
                  "fixed_links": len(products.source_list(p))},
        "runs": runs[:20],
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
    return {"site": site, "checks": website.site_checks(p) if site else None,
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
    return {"history": citations.history(), "sections": {k: len(v) for k, v in citations.prompt_sections().items()},
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


def build_product_page(b):
    p, questions, competitors = page_context(b.get("slug", ""))
    version = "ai" if b.get("version") == "ai" else "template"
    return catalog.build(p, str(b.get("id", "")), questions, competitors, version,
                         b.get("provider") or "gemini", b.get("model") or "gemini-2.5-flash",
                         fresh=bool(b.get("fresh")))


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

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path in ("/", "/index.html"):
                return self.static("index.html")
            if url.path.startswith("/static/"):
                return self.static(url.path[len("/static/"):])
            if url.path == "/api/state":
                return self.send(200, state())
            if url.path == "/api/product":
                return self.send(200, product_info(q.get("slug", "")))
            if url.path == "/api/job":
                return self.send(200, JOB.as_dict() if JOB else None)
            if url.path.startswith("/files/"):
                return self.file(urllib.parse.unquote(url.path[len("/files/"):]), q.get("download") == "1")
            if url.path == "/api/site":
                return self.send(200, site_state(q.get("slug", "")))
            if url.path == "/api/site/page":
                return self.send(200, site_page(q.get("slug", ""), q.get("id", "")))
            if url.path == "/api/site/wiki":
                return self.send(200, website.wiki_blocks(products.get(q.get("slug", ""))))
            if url.path == "/api/citations":
                return self.send(200, citations_state(q.get("slug", "")))
            if url.path == "/api/citations/run":
                return self.send(200, citations.run_summary(q.get("run", "")))
            if url.path == "/api/citations/prompt":
                return self.send(200, citations_prompt(q))
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
                else:
                    products.add_custom(products.get(b["slug"]), b.get("text", ""))
            elif path == "/api/questions/delete":
                if b.get("kind") == "standard":
                    products.delete_standard(b["id"])
                else:
                    products.delete_custom(products.get(b["slug"]), b["id"])
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
            elif path == "/api/provider/remove":
                ai.remove_provider(b["id"])
            elif path == "/api/import/extract":
                text = products.extract_text(b["filename"], base64.b64decode(b["data"]))
                draft = products.draft_from_brochure(text, b.get("provider", "gemini"),
                                                     b.get("model", "gemini-2.5-flash"))
                return self.send(200, {"draft": draft, "words": len(text.split())})
            elif path == "/api/import/save":
                return self.send(200, {"slug": products.create_product(b.get("draft", {}))})
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
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
