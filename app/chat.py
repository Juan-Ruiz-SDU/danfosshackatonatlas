"""
The assistant panel on the right of the app: a chat with the Ollama model on the
team's server (the address in Settings > Ollama, e.g. http://10.126.128.116:11434/).

The answer is streamed from Ollama into memory; the page asks /api/chat/poll every
half second and shows the text as it grows. Nothing is saved on the server.

The assistant knows what Atlas does (APP_GUIDE), which tab you are on, and the
facts of the product picked at the top, so it can explain results and answer
product questions from the wiki. It is told to say so when the wiki has no answer.
"""
import json
import threading
import time
import urllib.error
import urllib.request
import uuid

import ai
import products

CHATS = {}
LOCK = threading.Lock()
MAX_FACTS = 6000      # characters of the fact sheet in the system prompt
MAX_TURNS = 12        # earlier messages sent back to the model

APP_GUIDE = """You are the assistant inside Atlas, a tool of a Danfoss hackathon team. Atlas finds the
version of a product web page that AI search (Google's AI Overviews, Gemini) cites first. Its tabs:
- Run: writes the product page in several styles from the product wiki (the only source of facts),
  then a citation lab simulates Google's AI: BM25 picks the top pages for each buyer question and
  an AI answers and cites. It reports which version is cited most and, if the targets are missed,
  proposes wiki changes that a person accepts or declines.
  The "Section by section, verified citations" style finds sub-queries (Gemini's real searches,
  buyer questions), retrieves evidence for each with BM25 + embeddings + a reranker, writes one
  section per sub-query citing [ids], and checks every sentence against its cited evidence.
- Web page: a reconstruction of the Danfoss website section, edited with wiki blocks and trained
  against competitor pages; shows what Googlebot sees, BM25 per question and a fact check.
- Model by model: one page per model of the product family, from the fact sheet table.
- Citations: asks Gemini (with Google Search) the prompts and records which pages it cites and the
  share of the answer each one supports; compares them with our pages per sub-query; an AI reviewer
  explains why, with a rubric that ignores length and formatting.
- How it works: an embedding map of the evidence and sub-queries, and each step of the section writer.
Rules: answer in the user's language, briefly and concretely. For product facts use ONLY the
PRODUCT FACTS below and say when they do not contain the answer; never invent figures. Google treats
pages made to manipulate AI answers as spam, so recommend pages that add real, verified information."""


def system_prompt(slug, tab):
    parts = [APP_GUIDE, f"The user is on the '{tab or 'Run'}' tab."]
    if slug:
        try:
            p = products.get(slug)
            facts = products.generate_variants.facts_only(products.fact_sheet(p))
            parts.append(f"PRODUCT: {p['name']}\nPRODUCT FACTS (from the wiki):\n{facts[:MAX_FACTS]}")
        except Exception:  # noqa: BLE001  (no product or no fact sheet: chat about the app)
            pass
    return "\n\n".join(parts)


def _ollama():
    p = ai.providers().get("ollama")
    if not p:
        raise RuntimeError("No Ollama AI in Settings.")
    return p


def status():
    p = _ollama()
    reachable, installed = ai.ollama_status(p["base_url"])
    # local chat models only: "-cloud" models run on ollama.com, so the product data would leave the network
    chat_models = [m for m in installed
                   if "embed" not in m and "minicheck" not in m and not m.split(":")[-1].endswith("cloud")]
    return {"base_url": p["base_url"], "reachable": reachable, "models": chat_models,
            "default": next((m for m in p.get("models", []) if m in chat_models), chat_models[0] if chat_models else "")}


def start(messages, slug="", tab="", model=""):
    p = _ollama()
    st = status()
    model = model or st["default"]
    if model and model not in st["models"]:
        raise ValueError(f"'{model}' is not a local chat model on {p['base_url']}.")
    if not model:
        raise RuntimeError(f"No chat model is installed on the Ollama server at {p['base_url']}.")
    msgs = [{"role": m["role"], "content": str(m["content"])[:8000]}
            for m in messages[-MAX_TURNS:] if m.get("role") in ("user", "assistant") and m.get("content")]
    if not msgs or msgs[-1]["role"] != "user":
        raise ValueError("Write a message first.")
    cid = uuid.uuid4().hex[:12]
    st = {"text": "", "done": False, "error": None, "stop": False, "model": model, "started": time.time()}
    with LOCK:
        for k in [k for k, v in CHATS.items() if time.time() - v["started"] > 3600]:
            CHATS.pop(k, None)  # forget old answers
        CHATS[cid] = st
    payload = {"model": model, "stream": True,
               "messages": [{"role": "system", "content": system_prompt(slug, tab)}] + msgs,
               "options": {"temperature": 0.3, "num_ctx": int(p.get("num_ctx", 16384))}}
    if "think" in p:
        payload["think"] = bool(p["think"])
    threading.Thread(target=_run, args=(p, payload, st), daemon=True).start()
    return {"id": cid, "model": model}


def _run(p, payload, st):
    url = p["base_url"].rstrip("/") + "/api/chat"
    for _ in range(2):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1800) as resp:
                for line in resp:
                    if st["stop"]:
                        break  # closing the connection stops Ollama too
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise RuntimeError(chunk["error"])
                    st["text"] += (chunk.get("message") or {}).get("content", "")
                    if chunk.get("done"):
                        break
            st["text"] = ai.THINK_RE.sub("", st["text"]).strip()
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 400 and "think" in payload and "think" in body.lower():
                payload.pop("think")  # this model has no thinking switch
                continue
            st["error"] = f"Ollama error {e.code}: {body[:200]}"
            break
        except Exception as e:  # noqa: BLE001
            st["error"] = (f"Cannot reach Ollama at {p['base_url']} ({getattr(e, 'reason', e)}). "
                           "Check that the server is on and you are on the same network.")
            break
    st["done"] = True


def poll(cid):
    st = CHATS.get(cid)
    if not st:
        raise ValueError("Unknown chat")
    return {"text": st["text"], "done": st["done"], "error": st["error"], "model": st["model"]}


def stop(cid):
    st = CHATS.get(cid)
    if st:
        st["stop"] = True
