"""
Comparison pages pasted in the app: competitor product pages (and the current Danfoss
page) that every run tests the new Danfoss pages against.

The links live in the product's source list (sources.txt, "Brand | URL" per line).
Pages are downloaded into products/<slug>/fixed/, one file per link, named after the
link, with the link in the file's header. A link that cannot be downloaded gets a
plain-language reason, so the user knows what to do.
"""
import hashlib
import json
import re
import threading
import urllib.parse

import products

TARGET = "danfoss"
MIN_COMPETITORS = 2
URL_RE = re.compile(r"\A---\s*\n.*?^url:\s*(\S+)", re.DOTALL | re.MULTILINE)
FETCHING = {}           # slug -> link being downloaded right now
LOCK = threading.Lock()


def _disc():
    import pipeline  # noqa: F401  (puts lab/ on the path)
    import discover_sources
    return discover_sources


def key(url):
    return url.strip().rstrip("/").lower()


def list_path(p):
    return products.REPO / p["source_list"] if p.get("source_list") else p["folder"] / "sources.txt"


# --- reading and saving the links ---------------------------------------------------
def parse(text, danfoss):
    """Lines of the boxes in the app: a link, or 'Brand | link'. Returns [(brand, url)]."""
    disc, rows, seen = _disc(), [], set()
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip().strip(",;")
        if not line or line.startswith("#"):
            continue
        brand, url = [x.strip() for x in line.split("|", 1)] if "|" in line else ("", line)
        if url.startswith("www."):
            url = "https://" + url
        if not re.match(r"https?://[^\s/]+\.[^\s]+", url) or " " in url:
            raise ValueError(f"Line {n} is not a web link: “{line[:80]}”. Copy the address "
                             "from the browser's address bar (it starts with https://).")
        is_danfoss = TARGET in disc.domain_of(url)
        if danfoss and not is_danfoss:
            raise ValueError(f"“{url[:80]}” is not a danfoss.com page. Put competitor links in "
                             "the Competitor pages box.")
        if not danfoss and is_danfoss:
            raise ValueError(f"“{url[:80]}” is a Danfoss page. Put it in the box for the current "
                             "Danfoss page instead.")
        brand = "Danfoss" if danfoss else (brand or disc.brand_of(disc.domain_of(url)))
        if key(url) not in seen:
            seen.add(key(url))
            rows.append((brand, url))
    return rows


def save(p, danfoss_text, competitor_text):
    """Write the links to the product's list. Comments and links that stay keep their
    place (the lab's hand-made list keeps its notes); new links go at the end."""
    rows = parse(danfoss_text, True) + parse(competitor_text, False)
    wanted = {key(u): (b, u) for b, u in rows}
    path = list_path(p)
    old = path.read_text(encoding="utf-8").splitlines() if path.is_file() else \
        ["# Pages every run compares against.  Brand | link", "# Edited in the Atlas app."]
    out, kept = [], set()
    for line in old:
        s = line.strip()
        if s and not s.startswith("#") and "|" in s:
            k = key(s.split("|", 1)[1])
            if k not in wanted or k in kept:
                continue  # removed in the app
            kept.add(k)
            b, u = wanted[k]
            out.append(f"{b} | {u}")
        else:
            out.append(line)
    out += [f"{b} | {u}" for k, (b, u) in wanted.items() if k not in kept]
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return rows


# --- what is downloaded ------------------------------------------------------------------
def _failed_file(p):
    return p["folder"] / "fixed" / "_failed.json"


def _failed(p):
    try:
        return json.loads(_failed_file(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def saved_pages(p):
    """{link key: (file, words)} of every saved comparison page of this product."""
    out = {}
    for d in products.page_dirs(p):
        for f in d.glob("*.md"):
            head = f.read_text(encoding="utf-8", errors="replace")
            m = URL_RE.match(head[:2000])
            if m:
                out.setdefault(key(m.group(1)), (f, len(head.split())))
    return out


def friendly(err):
    e = str(err)
    low = e.lower()
    if "captcha" in low or "access denied" in low or "bot check" in low:
        return ("This site answered with a bot check (captcha or 'access denied') instead of the page. "
                "Use a page from another competitor instead.")
    if "403" in e or "401" in e or "429" in e:
        return "This site blocks automatic downloads. Use a page from another competitor instead."
    if "404" in e or "410" in e:
        return "Page not found. Open the link in your browser and copy the address again."
    if "certificate" in low or "ssl" in low:
        return "This site's security certificate cannot be checked from this network. Use another page."
    if "almost no text" in low or "needs javascript" in low:
        return ("The page shows almost no text, even after opening it in a browser, so the app "
                "cannot read it. Use another page from this competitor or another one.")
    if "timed out" in low or "timeout" in low or "getaddrinfo" in low or "urlopen error" in low:
        return "The site did not answer. Check the link, or try again later."
    return f"Could not download it ({e[:120]})."


def status(p):
    rows = products.source_list(p)
    saved, failed = saved_pages(p), _failed(p)
    busy = FETCHING.get(p["slug"])
    links = []
    for brand, url in rows:
        k = key(url)
        item = {"brand": brand, "url": url, "danfoss": brand.lower() == TARGET}
        if k in saved:
            item.update(state="ok", words=saved[k][1])
        elif busy is not None and key(busy) == k:
            item["state"] = "downloading"
        elif k in failed:
            item.update(state="failed", error=failed[k])
        else:
            item["state"] = "waiting" if busy is not None else "new"
        links.append(item)
    # pages from other places (Gemini discovery, the lab's folders) count too: same count
    # as the run uses
    import pipeline
    competitors = sum(d.brand.lower() != TARGET for d in pipeline.load_pages(p, 50))
    return {"links": links, "busy": busy is not None, "competitors": competitors,
            "min_competitors": MIN_COMPETITORS,
            "ready": competitors >= MIN_COMPETITORS, "list_file": str(list_path(p).relative_to(products.REPO))}


# --- downloading --------------------------------------------------------------------------
def page_header(brand, style, url, title=""):
    return (f"---\nbrand: {brand}\nstyle: {style}\nurl: {url}\n"
            + (f"title: {title}\n" if title else "") + "---\n")


def fetch_missing(p, log=print, step=None, cancelled=None):
    """Download every listed link that is not saved yet. Used by the app's 'Save and
    download' button and at the start of every run."""
    disc = _disc()
    folder = p["folder"] / "fixed"
    folder.mkdir(exist_ok=True)
    rows = products.source_list(p)
    listed = {key(u) for _, u in rows}
    # pages of links removed from the list are deleted (only in fixed/, which the app owns)
    for f in folder.glob("*.md"):
        m = URL_RE.match(f.read_text(encoding="utf-8", errors="replace")[:2000])
        if m and key(m.group(1)) not in listed:
            f.unlink()
    saved, failed = saved_pages(p), {k: v for k, v in _failed(p).items() if k in listed}
    todo = [(b, u) for b, u in rows if key(u) not in saved]
    for i, (brand, url) in enumerate(todo):
        if cancelled and cancelled():
            break
        FETCHING[p["slug"]] = url
        if step:
            step("Downloading the comparison pages", i, len(todo))
        name = f"{re.sub(r'[^a-z0-9]+', '_', brand.lower()).strip('_')}_{hashlib.sha1(key(url).encode()).hexdigest()[:8]}.md"
        try:
            try:
                text = disc.download(url)
            except Exception as e:  # noqa: BLE001
                if "javascript" not in str(e).lower():
                    raise
                text = ""  # a "please enable JavaScript" page: the browser may still read it
            if len(text.split()) < 80:
                log(f"  {url}: little text without JavaScript, opening it in a browser ...")
                text = with_browser(url)
        except (Exception, SystemExit) as e:  # noqa: BLE001  (the lab's downloader exits on errors)
            failed[key(url)] = friendly(e)
            log(f"  could not download {url}: {failed[key(url)]}")
            continue
        style = "original" if brand.lower() == TARGET else "competitor"
        (folder / name).write_text(page_header(brand, style, url) + text + "\n", encoding="utf-8")
        failed.pop(key(url), None)
        log(f"  saved {brand}: {url} ({len(text.split())} words)")
    FETCHING.pop(p["slug"], None)
    _failed_file(p).write_text(json.dumps(failed, indent=1), encoding="utf-8")


def with_browser(url):
    """The page's text after its JavaScript ran (the same headless browser as the Web page
    tab). Raises if there is no browser, the site shows a bot check, or there is still
    almost no text."""
    import website
    from fetch_sources import html_to_text
    browser = website.find_browser()
    if not browser:
        raise ValueError("almost no text (needs JavaScript, and no Edge or Chrome was found)")
    import shutil
    import tempfile
    profile = tempfile.mkdtemp(prefix="atlas-browser-")
    try:
        text = html_to_text(website.render_with_browser(browser, url, profile))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if len(text.split()) < 80:
        raise ValueError("almost no text")
    return text


def start_fetch(p):
    with LOCK:
        if p["slug"] in FETCHING:
            return
        FETCHING[p["slug"]] = ""

    def work():
        try:
            fetch_missing(p, log=lambda m: None)
        finally:
            FETCHING.pop(p["slug"], None)
    threading.Thread(target=work, daemon=True).start()


def boxes(p):
    """The links as the two boxes in the app show them."""
    disc = _disc()
    dan, comp = [], []
    for brand, url in products.source_list(p):
        if brand.lower() == TARGET:
            dan.append(url)
        else:
            auto = disc.brand_of(disc.domain_of(url))
            comp.append(url if brand == auto else f"{brand} | {url}")
    return {"box_danfoss": "\n".join(dan), "box_competitors": "\n".join(comp)}


def google_link(p):
    q = p.get("keyword") or " ".join(x for x in (p.get("product_type"), p.get("application") and
                                                  "for " + p["application"]) if x) or p["name"]
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)
