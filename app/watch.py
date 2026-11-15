"""
Watch: news that means the team should test again.

AI models are renewed often and each one knows the web only up to a date, and Google changes
how pages earn authority. Either can make today's results stale. Atlas checks Google News
(public RSS, no key) on a schedule and warns when:

  model       a Gemini model newer than the ones Atlas uses comes out (Atlas's judge JEV and
              the Citations agent run on Gemini). With a Gemini key it also reads Google's
              official model list and warns about model names it has not seen before.
  authority   Google changes how it ranks or trusts pages: core or spam updates, E-E-A-T,
              site reputation, AI Overviews / AI Mode.

Each new alert shows in the app and is sent by email in a direct tone. The address is
invented (atlas-alerts@example.com: example.com is reserved and never receives mail) until a
real one is set in Settings › Alerts, with an SMTP server. Without SMTP the email is saved
as an .eml file in app/outbox/ so it can be read or forwarded.

Settings, all in .env: ALERT_EMAIL, SMTP_HOST, SMTP_PORT (587 STARTTLS, 465 SSL), SMTP_USER,
SMTP_PASSWORD, SMTP_FROM, WATCH_HOURS (default 24), CITATIONS_EVERY_DAYS (0 = off: refresh the
Citations tab automatically every N days).
"""
import datetime
import email.message
import email.utils
import json
import os
import pathlib
import re
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import ai

APP = pathlib.Path(__file__).resolve().parent
STATE = APP / "cache" / "watch.json"
OUTBOX = APP / "outbox"
DEFAULT_TO = "atlas-alerts@example.com"  # invented; set ALERT_EMAIL in Settings so mail really arrives
GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
FEEDS = {
    "model": ["Google Gemini new model release when:30d", "Gemini model launch Google DeepMind when:30d"],
    "authority": ["Google search core update when:30d", "Google E-E-A-T update when:30d",
                  "Google AI Overviews ranking change when:30d", "Google site reputation abuse update when:30d"],
}
MODEL_RE = re.compile(r"\bGemini\s+(\d+(?:\.\d+)?)(?:\s+(Pro|Flash[- ]Lite|Flash|Ultra|Nano|Deep Think))?", re.I)
AUTH_RE = re.compile(r"core update|spam update|helpful content|E-E-A-T|\bEEAT\b|site reputation|"
                     r"ranking (?:update|change|system)|AI Overviews?|AI Mode|authority", re.I)
LOCK = threading.Lock()


# --- state ----------------------------------------------------------------------------------
def _load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seen": [], "max_version": None, "api_models": None, "alerts": [], "last_check": None, "last_error": None}


def _save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    st["seen"] = st["seen"][-2000:]
    st["alerts"] = st["alerts"][-100:]
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")


def config():
    ai.load_env()
    e = os.environ.get
    return {"to": e("ALERT_EMAIL") or DEFAULT_TO, "invented": not e("ALERT_EMAIL"),
            "smtp_host": e("SMTP_HOST", ""), "smtp_port": e("SMTP_PORT", ""), "smtp_user": e("SMTP_USER", ""),
            "smtp_from": e("SMTP_FROM", ""), "has_password": bool(e("SMTP_PASSWORD")),
            "hours": float(e("WATCH_HOURS") or 24), "citations_days": float(e("CITATIONS_EVERY_DAYS") or 0)}


def _gemini_versions():
    """Version numbers of the Gemini models Atlas is set to use (app/providers.json)."""
    models = (ai.providers().get("gemini") or {}).get("models", [])
    return [float(m.group(1)) for x in models for m in [re.search(r"gemini-(\d+(?:\.\d+)?)", x)] if m]


# --- reading the news ----------------------------------------------------------------------
def _fetch(query):
    url = GNEWS.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Atlas news watch)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        items.append({"title": title, "link": (it.findtext("link") or "").strip(),
                      "date": (it.findtext("pubDate") or "").strip(),
                      "source": (src.text or "").strip() if src is not None else ""})
    return items


def _api_models():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                 headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    return sorted(m["name"].split("/")[-1] for m in data.get("models", []) if "gemini" in m.get("name", ""))


def check(log=lambda m: None):
    """Read the feeds, record what is new, raise alerts and email them. Returns the new alerts."""
    with LOCK:
        ai.load_env()
        st = _load()
        first = st["last_check"] is None
        seen = set(st["seen"])
        known = max(_gemini_versions() + ([st["max_version"]] if st["max_version"] else []) or [0])
        new_alerts, errors = [], []

        models, auth = {}, []
        for kind, queries in FEEDS.items():
            for q in queries:
                try:
                    items = _fetch(q)
                except Exception as e:  # noqa: BLE001  (offline, blocked: try the others)
                    errors.append(f"{q}: {e}")
                    continue
                log(f"{q}: {len(items)} stories")
                for it in items:
                    key = it["link"] or it["title"]
                    is_new = key not in seen
                    seen.add(key)
                    for m in MODEL_RE.finditer(it["title"]):
                        v = float(m.group(1))
                        if v > known:
                            name = f"Gemini {m.group(1)}" + (f" {m.group(2).title()}" if m.group(2) else "")
                            models.setdefault(v, {"name": name, "items": []})["items"].append(it)
                    if kind == "authority" and is_new and AUTH_RE.search(it["title"]):
                        auth.append(it)

        if models:
            top = max(models)
            names = sorted({x["name"] for x in models.values()})
            items = [i for v in sorted(models, reverse=True) for i in models[v]["items"]][:8]
            new_alerts.append(_alert("model", f"New Gemini model in the news: {', '.join(names)}", names, items))
            st["max_version"] = top

        try:
            api = _api_models()
        except Exception as e:  # noqa: BLE001
            api, _ = None, errors.append(f"Gemini model list: {e}")
        if api is not None:
            if st["api_models"] is not None:
                fresh = [m for m in api if m not in st["api_models"]]
                if fresh:
                    new_alerts.append(_alert("model", f"New Gemini models in Google's API: {', '.join(fresh[:6])}",
                                             fresh, []))
            st["api_models"] = api

        if auth and not first:  # the first check only learns what is already out there
            new_alerts.append(_alert("authority", "Google news about ranking and authority", [], auth[:10]))
        elif auth and first:
            log(f"First check: {len(auth)} recent ranking stories recorded as known (no alert).")

        for a in new_alerts:
            a["email"] = send(a)
            log(f"ALERT: {a['title']} ({a['email']})")
        st["seen"] = list(seen)
        st["alerts"] += new_alerts
        st["last_check"] = datetime.datetime.now().isoformat(timespec="seconds")
        st["last_error"] = "; ".join(errors)[:600] or None
        _save(st)
        return new_alerts


def _alert(kind, title, names, items):
    return {"id": f"{kind}-{int(time.time() * 1000)}", "kind": kind, "title": title, "names": names,
            "items": items, "created": datetime.datetime.now().isoformat(timespec="seconds"), "read": False}


# --- email ----------------------------------------------------------------------------------
def compose(a):
    """Subject and body in a direct tone: what happened, why it matters, what to do."""
    used = ", ".join((ai.providers().get("gemini") or {}).get("models", [])) or "Gemini"
    lines = []
    if a["kind"] == "model":
        many = len(a["names"]) > 1
        subject = f"Atlas: {a['title'].split(': ', 1)[-1]} {'are' if many else 'is'} out. Re-test the pages"
        lines += [f"{a['title']}.", "",
                  f"Why it matters: Atlas's judge (JEV) and the Citations tab run on {used}. A newer model "
                  "knows the web up to a later date and may cite different pages, so the last results "
                  "may no longer hold. The pages are probably due for a new round of training.", "",
                  "Do this:",
                  "1. Add the new model in Atlas > Settings (Gemini models) and pick it for JEV in Run.",
                  "2. Citations > Ask Gemini: see which pages the new model cites.",
                  "3. Run the citation test again and compare it with the last report."]
    else:
        subject = "Atlas: Google changed how it ranks pages. Check the site"
        lines += ["Google published changes that can affect how pages earn authority or get cited in "
                  "AI Overviews.", "",
                  "Do this:",
                  "1. Read the stories below.",
                  "2. Citations > Ask Gemini: check whether Danfoss's citations moved.",
                  "3. Check that wiki/guidelines/site-structure.md and page-structure.md still match "
                  "Google's guidance, then re-test the pages."]
    if a["items"]:
        lines += ["", "Sources:"] + [f"- {i['title']} ({i['source'] or 'news'}, {i['date'][:16]})\n  {i['link']}"
                                     for i in a["items"]]
    if a["names"] and a["kind"] == "model" and not a["items"]:
        lines += ["", "New model names: " + ", ".join(a["names"])]
    lines += ["", "-- ", "Sent by Atlas. Change the address or turn alerts off in Atlas > Settings > Alerts."]
    return subject, "\n".join(lines)


def send(a, test=False):
    """Send the alert by email (SMTP from .env), or save it in app/outbox/ when no server is set."""
    cfg = config()
    subject, body = compose(a)
    if test:
        subject = "Atlas: test email. Alerts reach this address"
    msg = email.message.EmailMessage()
    msg["Subject"], msg["To"] = subject, cfg["to"]
    msg["From"] = cfg["smtp_from"] or cfg["smtp_user"] or "atlas@localhost"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(body if not test else "This is a test from Atlas. New-model and ranking alerts will look like this.\n\n" + body)
    if not cfg["smtp_host"] or cfg["invented"]:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        f = OUTBOX / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{a['kind']}.eml"
        f.write_bytes(bytes(msg))
        why = "the address is invented" if cfg["invented"] else "no SMTP server is set"
        return f"saved in app/outbox/{f.name} ({why})"
    try:
        port = int(cfg["smtp_port"] or 587)
        if port == 465:
            s = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=30, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(cfg["smtp_host"], port, timeout=30)
            s.starttls(context=ssl.create_default_context())
        with s:
            if cfg["smtp_user"]:
                s.login(cfg["smtp_user"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return f"sent to {cfg['to']}"
    except Exception as e:  # noqa: BLE001
        return f"not sent: {e}"


# --- for the app --------------------------------------------------------------------------
def status():
    st = _load()
    cfg = config()
    nxt = None
    if st["last_check"]:
        nxt = (datetime.datetime.fromisoformat(st["last_check"]) + datetime.timedelta(hours=cfg["hours"])).isoformat(timespec="minutes")
    return {"config": cfg, "last_check": st["last_check"], "next_check": nxt, "last_error": st["last_error"],
            "alerts": list(reversed(st["alerts"]))[:30], "unread": sum(not a["read"] for a in st["alerts"]),
            "watching": {"gemini_versions": sorted(set(_gemini_versions() + ([st["max_version"]] if st["max_version"] else []))),
                         "api_models": len(st["api_models"] or [])}}


def mark_read():
    with LOCK:
        st = _load()
        for a in st["alerts"]:
            a["read"] = True
        _save(st)


def test_email():
    return send({"kind": "model", "title": "Test", "names": [], "items": []}, test=True)


def start_scheduler(citations_update=None, last_citations=None):
    """Check every WATCH_HOURS (first check a minute after start); optionally refresh the
    Citations tab every CITATIONS_EVERY_DAYS days."""
    def loop():
        time.sleep(60)
        while True:
            try:
                cfg, st = config(), _load()
                last = st["last_check"]
                due = not last or datetime.datetime.now() - datetime.datetime.fromisoformat(last) >= datetime.timedelta(hours=cfg["hours"])
                if due:
                    check()
                if cfg["citations_days"] and citations_update and last_citations:
                    when = last_citations()
                    if not when or datetime.datetime.now() - when >= datetime.timedelta(days=cfg["citations_days"]):
                        citations_update()
            except Exception:  # noqa: BLE001  (never take the app down)
                pass
            time.sleep(1800)
    threading.Thread(target=loop, daemon=True).start()
