"""
Talking to AIs: the providers in providers.json (any OpenAI-compatible chat API),
the API keys in .env, and Gemini with Google Search for source discovery.
"""
import hashlib
import http.client
import json
import os
import pathlib
import re
import socket
import time
import urllib.error
import urllib.request

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
PROVIDERS_FILE = APP / "providers.json"
ENV_FILE = REPO / ".env"
CACHE = APP / "cache"
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class Cancelled(Exception):
    """The user pressed Stop."""


class ConnectionLost(RuntimeError):
    """The connection to the AI dropped in the middle of an answer."""


# --- connections to Ollama -----------------------------------------------------------
# While Ollama reads a long prompt on a CPU, nothing is sent back for many minutes.
# Some networks (university or company Wi-Fi, routers) cut a connection that is silent
# that long. TCP keep-alive packets every 30 s keep it alive.
def _keepalive(sock):
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):  # Windows: on, after 30 s, every 10 s
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 30000, 10000))
        else:
            for opt, v in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 6)):
                if hasattr(socket, opt):
                    sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), v)
    except OSError:
        pass


class _KeepAliveConnection(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        _keepalive(self.sock)


class _KeepAliveHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_KeepAliveConnection, req)


OLLAMA = urllib.request.build_opener(_KeepAliveHandler)
# a dropped connection: the server restarted or reloaded the model, or the network cut it
DROPS = (ConnectionError, http.client.HTTPException)
KEEP_LOADED = "30m"  # ask Ollama to keep the model in memory between steps


def _dropped(e):
    return isinstance(e, DROPS) or isinstance(getattr(e, "reason", None), ConnectionError)


# --- keys (.env) ---------------------------------------------------------------
def load_env():
    """Read .env into os.environ. Values in .env win, so a key saved in the app
    takes effect without restarting."""
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")


def save_key(env_name, value):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_name or ""):
        raise ValueError("Key name must look like GEMINI_API_KEY")
    value = value.strip()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    lines = [l for l in lines if not l.strip().startswith(env_name + "=")]
    if value:
        lines.append(f"{env_name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.pop(env_name, None)
    load_env()


def has_key(env_name):
    load_env()
    return bool(os.environ.get(env_name)) if env_name else True


# --- providers -----------------------------------------------------------------
def providers():
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def add_provider(pid, label, base_url, key_env, models, sleep=0):
    pid = re.sub(r"[^a-z0-9_-]+", "-", pid.strip().lower()).strip("-")
    if not pid or not base_url.startswith(("http://", "https://")):
        raise ValueError("Give the AI a name and an http(s) address")
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    data[pid] = {"label": label.strip() or pid,
                 "base_url": base_url.strip().rstrip("/") + "/",
                 "key_env": (key_env or "").strip() or None,
                 "models": [m.strip() for m in models if m.strip()],
                 "sleep": float(sleep or 0)}
    PROVIDERS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return pid


def update_provider(pid, base_url=None, models=None):
    """Change an AI's address (e.g. the team's Ollama server IP) or its model list."""
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    if pid not in data or pid.startswith("_"):
        raise ValueError(f"Unknown AI '{pid}'")
    if base_url is not None:
        base_url = base_url.strip()
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("The address must start with http:// (e.g. http://10.126.128.116:11434/)")
        data[pid]["base_url"] = base_url.rstrip("/") + "/"
    if models is not None:
        data[pid]["models"] = [m.strip() for m in models if m.strip()]
    PROVIDERS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ollama_status(base_url):
    """(reachable, installed model names) of an Ollama server, checked in 3 seconds."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=3) as resp:
            return True, sorted(m["name"] for m in json.loads(resp.read()).get("models", []))
    except Exception:  # noqa: BLE001
        return False, []


def remove_provider(pid):
    data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    if pid in ("gemini", "ollama"):
        raise ValueError("Ollama and Gemini are built in and cannot be removed")
    data.pop(pid, None)
    PROVIDERS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --- chat ----------------------------------------------------------------------
def chat(provider_id, model, system, user, temperature=0.3, cancel=None, use_cache=True,
         log=print, salt=None, json_mode=False):
    """One answer from any provider. Answers are cached on disk, so re-running the
    same step costs nothing. A different salt (e.g. the repeat number) gets a new answer.
    json_mode asks the provider for valid JSON (OpenAI-compatible response_format,
    supported by Ollama and Gemini), which small local models need."""
    if json_mode:
        salt = f"{salt}|json"
    p = providers().get(provider_id)
    if not p:
        raise RuntimeError(f"Unknown AI '{provider_id}'. Check Settings.")
    load_env()
    key = os.environ.get(p["key_env"]) if p.get("key_env") else None
    if p.get("key_env") and not key:
        raise RuntimeError(f"No API key for {p['label']}. Add it in Settings.")

    h = hashlib.sha256(json.dumps([provider_id, model, system, user, temperature, salt]).encode()).hexdigest()
    path = CACHE / f"{h}.json"
    if use_cache and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))["text"]

    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": user}]
    is_ollama = p.get("type") == "ollama"
    if is_ollama:
        # Ollama's own API: lets us raise the context size (its default silently cuts
        # long prompts) and switch off "thinking", which is very slow on a CPU.
        # Every step uses the same context size (num_ctx in providers.json): a different
        # size makes Ollama reload the model, which can drop a request already running.
        payload = {"model": model, "messages": messages, "stream": False,
                   "keep_alive": p.get("keep_alive", KEEP_LOADED),
                   "options": {"temperature": temperature, "num_ctx": int(p.get("num_ctx", 16384))}}
        if "think" in p:
            payload["think"] = bool(p["think"])
        if json_mode:
            payload["format"] = "json"  # Ollama only writes valid JSON
        url = p["base_url"].rstrip("/") + "/api/chat"
    else:
        payload = {"model": model, "temperature": temperature, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        url = p["base_url"] + "chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    wait, drops = 10, 0
    opener = OLLAMA if is_ollama else urllib.request.build_opener()
    for attempt in range(6):
        if cancel and cancel():
            raise Cancelled()
        if p.get("sleep"):
            time.sleep(float(p["sleep"]))  # stay under free per-minute limits
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        try:
            # 30 minutes: a long page on a shared CPU can take that long
            with opener.open(req, timeout=1800) as resp:
                data = json.loads(resp.read())
            raw = data["message"]["content"] if is_ollama else data["choices"][0]["message"].get("content")
            text = THINK_RE.sub("", raw or "").strip()
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "text": text}), encoding="utf-8")
            return text
        except urllib.error.HTTPError as e:
            full = e.read().decode(errors="replace")
            detail = full[:400]
            if is_ollama and e.code == 400 and "think" in payload and "think" in full.lower():
                payload.pop("think")  # this model has no thinking switch: just ask again
                continue
            if is_ollama and e.code == 404:
                raise RuntimeError(f"Model '{model}' is not installed on the Ollama server at "
                                   f"{p['base_url']}. On that computer run:  ollama pull {model}")
            if e.code == 429 or e.code >= 500:
                if "PerDay" in full or "per day" in full.lower():
                    raise RuntimeError(f"The daily free quota of {p['label']} is used up. "
                                       "Run again tomorrow: finished answers are saved, so "
                                       "the run continues where it stopped.")
                log(f"    {p['label']} is busy ({e.code}), retrying in {wait}s ...")
                time.sleep(wait)
                wait = min(wait * 2, 120)
                continue
            raise RuntimeError(f"{p['label']} error {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, *DROPS) as e:
            if is_ollama and _dropped(e) and drops < 2:
                drops += 1
                log(f"    the connection to {p['label']} dropped ({getattr(e, 'reason', e)}), "
                    "asking again in 15 s ...")
                time.sleep(15)
                continue
            if is_ollama and _dropped(e):
                raise ConnectionLost(
                    f"The connection to {p['label']} at {p['base_url']} kept dropping. Check that "
                    "the server is on and nobody restarted it, then run again: finished steps "
                    "are saved.")
            if is_ollama or "localhost" in p["base_url"] or "127.0.0.1" in p["base_url"]:
                raise RuntimeError(
                    f"Cannot reach {p['label']} at {p['base_url']} ({getattr(e, 'reason', e)}). "
                    "If it is your own computer, open the Ollama app. If it is the team server, "
                    "check that it is on, that you are on the same Wi-Fi, and that the address "
                    "in Settings is its current IP.")
            log(f"    network error ({getattr(e, 'reason', e)}), retrying in {wait}s ...")
            time.sleep(wait)
            wait = min(wait * 2, 120)
    raise RuntimeError(f"Gave up on {p['label']} after 6 attempts. Check your connection or quota.")


def ollama_stream(provider_id, model, system, user, temperature=0.1, fmt=None,
                  on_token=None, cancel=None, on_open=None, num_ctx=None):
    """One Ollama answer, streamed so the caller can show progress and stop it.
    fmt="json" makes Ollama only produce valid JSON. on_token(n) is called with the
    number of tokens written so far. Returns (text, stats) where stats holds Ollama's
    own timings: prompt_eval_count/duration, eval_count/duration, load_duration (ns).
    on_open(resp) receives the open connection, so another thread can close it to stop."""
    p = providers().get(provider_id)
    if not p or p.get("type") != "ollama":
        raise RuntimeError(f"'{provider_id}' is not an Ollama AI")
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": user}]
    payload = {"model": model, "messages": messages, "stream": True,
               "keep_alive": p.get("keep_alive", KEEP_LOADED),
               "options": {"temperature": temperature,
                           "num_ctx": int(num_ctx or p.get("num_ctx", 16384))}}
    if "think" in p:
        payload["think"] = bool(p["think"])
    if fmt:
        payload["format"] = fmt
    url = p["base_url"].rstrip("/") + "/api/chat"
    for _ in range(2):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            parts, n, stats = [], 0, {}
            with OLLAMA.open(req, timeout=1800) as resp:
                if on_open:
                    on_open(resp)
                for line in resp:  # one JSON object per line
                    if cancel and cancel():
                        raise Cancelled()  # closing the connection stops Ollama too
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise RuntimeError(f"Ollama error: {chunk['error']}")
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        n += 1
                        if on_token:
                            on_token(n)
                    if chunk.get("done"):
                        stats = {k: chunk.get(k) for k in ("prompt_eval_count", "prompt_eval_duration",
                                                            "eval_count", "eval_duration", "load_duration")}
            if cancel and cancel():
                raise Cancelled()
            if not stats:  # the stream ended without Ollama's final "done" message
                raise ConnectionError("the answer was cut off")
            return THINK_RE.sub("", "".join(parts)).strip(), stats
        except urllib.error.HTTPError as e:
            full = e.read().decode(errors="replace")
            if e.code == 400 and "think" in payload and "think" in full.lower():
                payload.pop("think")
                continue
            if e.code == 404:
                raise RuntimeError(f"Model '{model}' is not installed on the Ollama server at "
                                   f"{p['base_url']}. On that computer run:  ollama pull {model}")
            raise RuntimeError(f"{p['label']} error {e.code}: {full[:400]}")
        except (urllib.error.URLError, OSError, ValueError, AttributeError) as e:
            if cancel and cancel():
                raise Cancelled() from None  # Stop closed the connection
            if isinstance(e, ValueError) and not isinstance(e, json.JSONDecodeError):
                raise
            if isinstance(e, urllib.error.URLError) and not _dropped(e):
                raise RuntimeError(
                    f"Cannot reach {p['label']} at {p['base_url']} ({getattr(e, 'reason', e)}). "
                    "Check that the server is on and you are on the same network.") from None
            raise ConnectionLost(
                f"Lost the connection to {p['label']} at {p['base_url']} ({getattr(e, 'reason', e)}). "
                "Check that the server is on and you are on the same network.") from None
    raise RuntimeError(f"{p['label']} refused the request")


def gemini_key():
    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Source discovery needs a Gemini API key. Add it in Settings.")
    return key


def parse_json(text):
    """The first JSON object in an AI answer (models like to wrap it in ```json)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("The AI did not return JSON")
    try:
        # strict=False accepts raw line breaks inside strings, which small models often write
        return json.loads(m.group(0), strict=False)
    except json.JSONDecodeError as e:
        raise ValueError(f"The AI's answer was not valid JSON ({e.msg})") from None
