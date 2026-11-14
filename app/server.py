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
import comparison  # noqa: E402
import pipeline  # noqa: E402
import products  # noqa: E402
import webpage  # noqa: E402


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
                       for k in pipeline.gv.STYLES],
            "job": JOB.as_dict() if JOB else None}


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
        "questions": products.questions(p), "fact_sheet": sheet, "fact_sheet_error": sheet_error,
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


def analyze_page(slug):
    """The Web page tab, from the saved copy (never downloads)."""
    p, questions, competitors = page_context(slug)
    try:
        allowed = pipeline.gv.allowed_numbers(products.fact_sheet(p))
    except ValueError:
        allowed = frozenset()
    return webpage.analyze(p, questions, competitors, allowed)


def copy_page(b):
    """Reverse-engineer the current page once (download, or a saved .html file),
    then show the analysis. `replace` also overwrites the edited copy."""
    p = products.get(b.get("slug", ""))
    url = (b.get("url") or danfoss_url(p)).strip()
    raw = None
    if b.get("data"):
        raw = base64.b64decode(b["data"]).decode("utf-8", errors="replace")
    elif not url.startswith(("http://", "https://")):
        raise ValueError("Give the address of the current Danfoss page (https://...).")
    wrote = webpage.create_copy(p, url, bool(b.get("replace")), raw, b.get("filename", ""))
    return {**analyze_page(p["slug"]), "copy_written": wrote}


def save_page(b):
    p = products.get(b.get("slug", ""))
    webpage.save_copy(p, str(b.get("text", "")))
    return analyze_page(p["slug"])


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
            if url.path == "/api/webpage":
                return self.send(200, analyze_page(q.get("slug", "")))
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
            elif path == "/api/webpage/copy":
                return self.send(200, copy_page(b))
            elif path == "/api/webpage/save":
                return self.send(200, save_page(b))
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
