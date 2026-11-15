"""
The live Danfoss page in the Web page tab.

danfoss.com cannot be shown in a frame of another site (its server forbids it), so
Atlas fetches the page at the moment you open it, the way a browser shows it (headless
Edge or Chrome, JavaScript run), and serves it from its own address:

- a <base> tag makes its images and styles load from danfoss.com;
- scripts are removed (the page is already rendered, and they would only break);
- links to other danfoss.com pages go through Atlas again, so you can browse inside
  the box; links elsewhere open in a new tab.

Only danfoss.com pages. Each page is kept 5 minutes in memory, so going back is instant.
"""
import html
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request

import website

CACHE, TTL = {}, 300
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>|<noscript\b.*?</noscript\s*>", re.S | re.I)
HREF_RE = re.compile(r'(<a\b[^>]*?\bhref=)(["\'])(.*?)\2', re.S | re.I)
TARGET_RE = re.compile(r'\starget=(["\']).*?\1', re.I)


def allowed(url):
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or "").lower()
    return p.scheme in ("http", "https") and (host == "danfoss.com" or host.endswith(".danfoss.com"))


def _fetch(url):
    browser = website.find_browser()
    if browser:
        profile = tempfile.mkdtemp(prefix="atlas-live-")
        try:
            return website.render_with_browser(browser, url, profile)
        finally:
            shutil.rmtree(profile, ignore_errors=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def _rewrite(raw, url):
    page = SCRIPT_RE.sub("", raw)

    def link(m):
        target = urllib.parse.urljoin(url, html.unescape(m.group(3)))
        if target.startswith(("mailto:", "tel:", "javascript:")) or "#" == m.group(3)[:1]:
            return m.group(0)
        if allowed(target):
            return f'{m.group(1)}{m.group(2)}/live?url={urllib.parse.quote(target, safe="")}{m.group(2)} target="_self"'
        return f'{m.group(1)}{m.group(2)}{html.escape(target)}{m.group(2)} target="_blank" rel="noopener"'
    page = re.sub(r"<a\b[^>]*>", lambda m: TARGET_RE.sub("", m.group(0)), page, flags=re.I)  # one target per link
    page = HREF_RE.sub(link, page)
    # the cookie banner needs its scripts to close, so it is hidden (nothing is accepted or stored)
    hide = ("<style>#cookie-information-template-wrapper,[class*='coi-banner'],[class*='coi-consent'],"
            "#onetrust-consent-sdk,#usercentrics-root{display:none!important}"
            "html,body{overflow:auto!important;position:static!important}</style>")
    base = f'<base href="{html.escape(url)}">' + hide
    if re.search(r"<head[^>]*>", page, re.I):
        page = re.sub(r"(<head[^>]*>)", r"\1" + base, page, count=1, flags=re.I)
    else:
        page = base + page
    return page


def page(url):
    """The live page as HTML for the frame. Raises ValueError with a readable reason."""
    url = (url or "").strip()
    if not allowed(url):
        raise ValueError("Only danfoss.com pages can be shown live.")
    hit = CACHE.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    out = _rewrite(_fetch(url), url)
    CACHE[url] = (time.time(), out)
    return out


def error_page(url, reason):
    return (f"<!doctype html><meta charset='utf-8'><body style='font:15px system-ui;padding:24px;color:#444'>"
            f"<h3>The page could not be loaded</h3><p>{html.escape(str(reason))}</p>"
            f"<p><a href='{html.escape(url)}' target='_blank' rel='noopener'>Open it on danfoss.com ↗</a></p></body>")
