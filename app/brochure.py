"""
Adding a product from a brochure, as a background job with a progress bar.

Reading a brochure with qwen3:8b on a CPU takes minutes, so it must not run inside
one web request (the browser gives up, or the user thinks it froze). The job runs in
a thread; the page asks /api/import/status every second.

Time remaining: Ollama first reads the whole prompt (no output yet), then writes the
answer token by token. Both speeds are measured on every import and saved in
app/cache/import_speed.json, so the estimate gets better each time.
"""
import json
import threading
import time
import traceback

import ai
import products

SPEED_FILE = ai.CACHE / "import_speed.json"
# first-time guesses for an 8B model on a CPU, replaced by measurements after one import
DEFAULT_SPEED = {"read_tps": 30.0, "write_tps": 4.0, "chars_per_token": 3.8,
                 "out_ratio": 0.25, "load_s": 15.0}
MAX_TRIES = 2


def _speeds():
    try:
        return json.loads(SPEED_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def speed_for(key):
    return {**DEFAULT_SPEED, **_speeds().get(key, {})}


def save_speed(key, measured):
    """Blend the new measurement into the saved one, so one odd run cannot ruin it."""
    allv = _speeds()
    old = {**DEFAULT_SPEED, **allv.get(key, {})}
    first = key not in allv
    allv[key] = {k: (measured[k] if first else 0.5 * old[k] + 0.5 * measured[k]) if k in measured else old[k]
                 for k in DEFAULT_SPEED}
    ai.CACHE.mkdir(parents=True, exist_ok=True)
    SPEED_FILE.write_text(json.dumps(allv, indent=2), encoding="utf-8")


class ImportJob:
    def __init__(self, filename, data, provider, model):
        self.filename, self.data, self.provider, self.model = filename, data, provider, model
        self.status, self.error, self.draft, self.words = "running", None, None, 0
        self.step, self.pct, self.left = "Starting", 0.0, None
        self.lines, self.stop, self.conn = [], False, None
        self.started = time.time()

    def log(self, msg):
        self.lines.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        del self.lines[:-100]

    def set(self, step, pct, left=None):
        if step != self.step:
            self.log(step)
        self.step, self.pct, self.left = step, max(self.pct, min(pct, 99.0)), left

    def cancelled(self):
        return self.stop

    def as_dict(self):
        return {"status": self.status, "error": self.error, "draft": self.draft,
                "words": self.words, "filename": self.filename, "step": self.step,
                "pct": round(self.pct, 1), "left": None if self.left is None else int(self.left),
                "elapsed": int(time.time() - self.started), "log": self.lines[-30:]}

    # --- the work --------------------------------------------------------------------
    def run(self):
        try:
            self.set("Reading the file", 1)
            text = products.extract_text(self.filename, self.data)
            self.data = None  # free the upload
            self.words = len(text.split())
            self.log(f"Found {self.words} words of text in {self.filename}")
            limit = products.brochure_limit(self.provider)
            if len(text) > limit:
                self.log(f"The brochure is long: the AI reads the first {limit} characters "
                         f"(about {len(text[:limit].split())} words)")
            prompt = products.DRAFT_PROMPT.format(text=text[:limit])
            p = ai.providers().get(self.provider)
            if not p:
                raise RuntimeError(f"Unknown AI '{self.provider}'. Check Settings.")
            last = None
            for attempt in range(1, MAX_TRIES + 1):
                if self.stop:
                    raise ai.Cancelled()
                if attempt > 1:
                    self.log(f"Asking again ({last})")
                try:
                    if p.get("type") == "ollama":
                        answer = self._ollama(p, prompt, attempt)
                    else:
                        answer = self._other(p, prompt)
                    self.draft = products.clean_draft(ai.parse_json(answer))
                    break
                except (ValueError, ai.ConnectionLost) as e:  # bad answer or dropped line
                    last = str(e).rstrip(".")
            else:
                raise RuntimeError(f"{last}. Try again, or pick a bigger model in the list.")
            self.pct, self.left, self.step = 100.0, 0, "Done: check the facts below"
            self.status = "done"
            self.log(f"Done in {int(time.time() - self.started)} s")
        except ai.Cancelled:
            self.status = "cancelled"
            self.log("Stopped by you.")
        except (ValueError, RuntimeError, KeyError) as e:
            self.status, self.error = "error", str(e)
            self.log("ERROR: " + str(e))
        except Exception as e:  # noqa: BLE001
            self.status, self.error = "error", f"Unexpected problem: {e}"
            self.log(traceback.format_exc())

    def _ollama(self, p, prompt, attempt):
        self.set("Connecting to Ollama", 2)
        reachable, installed = ai.ollama_status(p["base_url"])
        if not reachable:
            raise RuntimeError(
                f"Cannot reach Ollama at {p['base_url']}. If it is the team server, check that it "
                "is on, that you are on the same Wi-Fi, and that the address in Settings is its "
                "current IP. Or pick another AI in the list next to 'Read the brochure'.")
        names = set(installed) | {n.removesuffix(":latest") for n in installed}
        if installed and self.model not in names:
            raise RuntimeError(f"Model '{self.model}' is not installed on {p['base_url']}. "
                               f"Installed: {', '.join(installed)}. Or on that computer run:  "
                               f"ollama pull {self.model}")

        key = f"{p['base_url']}|{self.model}"
        sp = speed_for(key)
        prompt_tok = len(prompt) / sp["chars_per_token"]
        exp_out = min(max(prompt_tok * sp["out_ratio"], 400), 4000)
        read_s = sp["load_s"] + prompt_tok / sp["read_tps"]
        write_s = exp_out / sp["write_tps"]
        read_share = read_s / (read_s + write_s)
        lo = 3.0  # % already shown before the AI starts
        t0 = time.time()
        state = {"first": None}
        label = "The AI is reading the brochure" + (" (second try)" if attempt > 1 else "")

        # while Ollama reads the prompt nothing comes back: move the bar by the clock
        def ticker():
            while state["first"] is None and self.status == "running" and not self.stop:
                el = time.time() - t0
                frac = min(el / read_s, 0.97)
                self.set(label, lo + (100 - lo) * read_share * frac, max(read_s - el, 5) + write_s)
                time.sleep(1)
        threading.Thread(target=ticker, daemon=True).start()

        def on_token(n):
            now = time.time()
            if state["first"] is None:
                state["first"] = now
            nonlocal exp_out
            if n > exp_out * 0.95:
                exp_out = n * 1.15  # longer than expected: stretch the estimate
            gen_el = now - state["first"]
            rate = n / gen_el if gen_el > 5 and n > 20 else sp["write_tps"]
            frac = n / exp_out
            self.set("The AI is writing the fact sheet" + (" (second try)" if attempt > 1 else ""),
                     lo + (100 - lo) * (read_share + (1 - read_share) * frac),
                     (exp_out - n) / max(rate, 0.1))

        try:
            text, st = ai.ollama_stream(self.provider, self.model, "", prompt, temperature=0.1,
                                        fmt="json", on_token=on_token, cancel=self.cancelled,
                                        on_open=lambda r: setattr(self, "conn", r))
        finally:
            state["first"] = state["first"] or time.time()  # stop the ticker
        self._learn(key, prompt, st)
        return text

    def _learn(self, key, prompt, st):
        try:
            pc, pd = st.get("prompt_eval_count"), st.get("prompt_eval_duration")
            ec, ed = st.get("eval_count"), st.get("eval_duration")
            m = {}
            if pc and pd:
                m["read_tps"] = pc / (pd / 1e9)
                m["chars_per_token"] = len(prompt) / pc
            if ec and ed:
                m["write_tps"] = ec / (ed / 1e9)
            if pc and ec:
                m["out_ratio"] = ec / pc
            if st.get("load_duration"):
                m["load_s"] = st["load_duration"] / 1e9
            if m:
                save_speed(key, m)
                self.log("Speed: reads {:.0f} tokens/s, writes {:.1f} tokens/s (saved for next time)"
                         .format(m.get("read_tps", 0), m.get("write_tps", 0)))
        except Exception:  # noqa: BLE001  (an estimate must never break the import)
            pass

    def _other(self, p, prompt):
        """Cloud AIs answer in one piece: move the bar by the clock against a rough guess."""
        est = max(float(p.get("est_write", 30)), 10)
        t0, box = time.time(), {}

        def work():
            try:
                box["text"] = ai.chat(self.provider, self.model, "", prompt, temperature=0.1,
                                      use_cache=False, cancel=self.cancelled, log=self.log)
            except BaseException as e:  # noqa: BLE001
                box["err"] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        while th.is_alive():
            if self.stop:
                raise ai.Cancelled()
            el = time.time() - t0
            self.set(f"{p['label']} is reading the brochure", 3 + 94 * min(el / est, 0.97),
                     max(est - el, 3))
            th.join(1)
        if "err" in box:
            raise box["err"]
        return box["text"]


IMPORT = None
LOCK = threading.Lock()


def start(filename, data, provider, model):
    global IMPORT
    with LOCK:
        if IMPORT and IMPORT.status == "running":
            raise ValueError("A brochure is already being read. Wait for it, or press Stop.")
        IMPORT = ImportJob(filename, data, provider, model)
    threading.Thread(target=IMPORT.run, daemon=True).start()


def status():
    return IMPORT.as_dict() if IMPORT else None


def stop():
    if IMPORT:
        IMPORT.stop = True
        try:
            if IMPORT.conn:
                # closing the socket handle wakes the waiting read at once, even while Ollama
                # is still reading the prompt (shutdown() alone does not, on Windows).
                # detach() first so Python never closes the same handle twice.
                import socket
                sk = IMPORT.conn.fp.raw._sock
                try:
                    sk.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                socket.close(sk.detach())
        except Exception:  # noqa: BLE001
            pass


def clear():
    global IMPORT
    with LOCK:
        if IMPORT and IMPORT.status != "running":
            IMPORT = None
