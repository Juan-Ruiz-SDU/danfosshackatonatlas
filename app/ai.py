"""
Talking to AIs: the providers in providers.json (any OpenAI-compatible chat API),
the API keys in .env, and Gemini with Google Search for source discovery.
"""
import hashlib
import json
import os
import pathlib
import re
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
         log=print, salt=None):
    """One answer from any provider. Answers are cached on disk, so re-running the
    same step costs nothing. A different salt (e.g. the repeat number) gets a new answer."""
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
        payload = {"model": model, "messages": messages, "stream": False,
                   "options": {"temperature": temperature, "num_ctx": int(p.get("num_ctx", 16384))}}
        if "think" in p:
            payload["think"] = bool(p["think"])
        url = p["base_url"].rstrip("/") + "/api/chat"
    else:
        payload = {"model": model, "temperature": temperature, "messages": messages}
        url = p["base_url"] + "chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    wait = 10
    for attempt in range(6):
        if cancel and cancel():
            raise Cancelled()
        if p.get("sleep"):
            time.sleep(float(p["sleep"]))  # stay under free per-minute limits
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
        try:
            # 30 minutes: a long page on a shared CPU can take that long
            with urllib.request.urlopen(req, timeout=1800) as resp:
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
        except (urllib.error.URLError, TimeoutError) as e:
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
    return json.loads(m.group(0))
