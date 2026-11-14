"""
The "Web page" tab: a reconstruction of a section of Danfoss's website (for
example the heat exchanger catalog), shown as a small website inside Atlas, that
the team edits page by page to make it better for Googlebot and AI search.

  copy_site()      reverse-engineer the section once: every page is read twice,
                   as a crawler without JavaScript sees it (urllib) and as a
                   browser shows it (Edge/Chrome headless, runs JavaScript), and
                   saved as a snapshot (reference) plus an editable copy
  render_site()    the copies as a static website that looks like Danfoss's:
                   header, menu, breadcrumbs, catalog tiles, footer, links
                   between the pages, sitemap.xml
  site_checks()    how well the site spreads authority: click depth, links
                   between pages, orphan pages, sitemap, text without JavaScript
  page_analysis()  one page: changes vs the snapshot, crawler checks, what
                   Googlebot sees, BM25 per question (see webpage.py)

Files, in products/<product>/webpage/:
  site.json                   the pages and how they link (the map)
  site/<page>/original.md     snapshot of Danfoss's page (do not edit)
  site/<page>/original.json   what the copy found: download, checks, links
  site/<page>/page.md         YOUR copy of the page: edit it
  site/<page>.html            the page as rendered for the mini website
  sitemap.xml                 every page, with its address and last change
  cache/                      downloaded HTML (not committed)
"""
import datetime
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(APP))
import products  # noqa: E402
import webpage  # noqa: E402

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/microsoft-edge",
]


# --- reading pages -------------------------------------------------------------------
def find_browser():
    """A Chromium browser to render JavaScript pages (ATLAS_BROWSER overrides)."""
    for b in [os.environ.get("ATLAS_BROWSER", "")] + BROWSERS:
        if b and pathlib.Path(b).is_file():
            return b
    return None


def render_with_browser(browser, url, profile):
    """The page's HTML after its JavaScript ran (headless browser, --dump-dom)."""
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={profile}", "--virtual-time-budget=12000", "--dump-dom", url]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=150)
    except subprocess.TimeoutExpired:
        raise ValueError(f"The browser took too long to show {url}")
    text = out.stdout.decode("utf-8", errors="replace")
    if len(text) < 500:
        raise ValueError(f"The browser returned no page for {url}")
    why = webpage.fetch_sources.block_reason(text)
    if why:
        raise ValueError(f"The site answered with a {why} instead of {url}. " + webpage.BLOCK_HELP)
    return text


def norm_url(u):
    """Same page, same key: no query or fragment, trailing slash on folder paths."""
    s = urllib.parse.urlsplit(u)
    path = s.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return urllib.parse.urlunsplit((s.scheme, s.netloc.lower(), path, "", ""))


def page_id(url, used):
    parts = [x for x in urllib.parse.urlsplit(url).path.split("/") if x]
    base = re.sub(r"[^a-z0-9-]+", "-", (parts[-1] if parts else "home").lower()).strip("-")[:70] or "page"
    pid, k = base, 2
    while pid in used:
        pid, k = f"{base}-{k}", k + 1
    used.add(pid)
    return pid


def content_links(items, base):
    """Absolute addresses linked from a page's content (not menus or footers)."""
    out = []
    for it in items:
        if it["kind"] == "p" and it.get("href"):
            out.append(it["href"])
        elif it["kind"] == "cards":
            out += [c["href"] for c in it["items"]]
        for t in [it.get("text", "")] + [x for x in it.get("items", []) if isinstance(x, str)]:
            out += [m.group(2) for m in webpage.MD_LINK_RE.finditer(t)]
    seen, res = set(), []
    for h in out:
        a = norm_url(urllib.parse.urljoin(base, h))
        if a.startswith("http") and a not in seen:
            seen.add(a)
            res.append(a)
    return res


# --- paths and the site map ------------------------------------------------------------
def paths(p):
    folder = p["folder"] / "webpage"
    return {"folder": folder, "site": folder / "site", "map": folder / "site.json",
            "cache": folder / "cache", "sitemap": folder / "sitemap.xml",
            "lab": (REPO / p["restructured_dir"] if p.get("restructured_dir") else folder) / "restructured_1.md"}


def page_paths(p, pid):
    d = paths(p)["site"] / pid
    return {"dir": d, "original_md": d / "original.md", "original_json": d / "original.json",
            "copy": d / "page.md", "html": paths(p)["site"] / f"{pid}.html"}


def load_map(p):
    m = paths(p)["map"]
    return json.loads(m.read_text(encoding="utf-8")) if m.is_file() else None


def save_map(p, site):
    paths(p)["map"].write_text(json.dumps(site, indent=1, ensure_ascii=False), encoding="utf-8")


def default_start(p, danfoss_url):
    """The catalog to copy: product.json 'site_start', else the Danfoss page itself."""
    return p.get("site_start") or danfoss_url


# --- copying the site --------------------------------------------------------------------
def copy_site(p, start_url, also=(), max_pages=15, replace=False, log=print, cancelled=lambda: False):
    """Reverse-engineer a section of the site, starting at start_url, following
    the links in the pages' content that stay inside the start address, up to two
    clicks deep and max_pages pages. `also` adds pages that must be in it (the
    product's own Danfoss page). Existing edited copies are kept unless replace."""
    pp = paths(p)
    browser = find_browser()
    log(f"Browser for JavaScript pages: {browser or 'none found (pages are read without JavaScript)'}")
    start = norm_url(start_url)
    prefix = start
    queue = [(start, 0, None)] + [(norm_url(u), 9, None) for u in also if u]
    seen, pages, used = set(), [], set()
    profile = tempfile.mkdtemp(prefix="atlas-browser-")
    pp["cache"].mkdir(parents=True, exist_ok=True)
    try:
        while queue and len(pages) < max_pages:
            if cancelled():
                raise RuntimeError("Stopped by you.")
            url, depth, parent = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            log(f"Reading {url}")
            raw_info = None
            try:
                raw_info = webpage.fetch(url)  # what a crawler without JavaScript gets
            except ValueError as e:
                log(f"  without JavaScript: {e}")
            final = norm_url(raw_info["final_url"]) if raw_info else url
            if final in [x["final_url"] for x in pages]:
                continue
            seen.add(final)
            rendered = None
            if browser:
                try:
                    rendered = render_with_browser(browser, final, profile)
                except ValueError as e:
                    log(f"  with JavaScript: {e}")
            source_html = rendered or (raw_info or {}).get("html")
            if not source_html:
                log("  skipped: could not read it")
                continue
            meta, blocks = webpage.parse_page(source_html)
            if len(webpage.words_of(blocks)) < 40:
                log("  skipped: almost no text")
                continue
            raw_words = 0
            if raw_info:
                _, raw_blocks = webpage.parse_page(raw_info["html"])
                raw_words = len(webpage.words_of(raw_blocks))
            items, removed = webpage.structure(blocks)
            pid = page_id(final, used)
            pg = page_paths(p, pid)
            pg["dir"].mkdir(parents=True, exist_ok=True)
            (pp["cache"] / f"{pid}.html").write_text(source_html, encoding="utf-8")
            checks = webpage.audit(meta, blocks, raw_info) if raw_info else webpage.audit(meta, blocks)
            checks = [c for c in checks if c["check"] != "Words readable without JavaScript"]
            words_js = len(webpage.words_of(blocks))
            checks.append({"check": "Words readable without JavaScript", "value": f"{raw_words} of {words_js}",
                           "status": "ok" if raw_words >= 0.9 * words_js else "bad" if raw_words < 0.5 * words_js else "warn",
                           "note": "" if raw_words >= 0.9 * words_js else
                           "Most of the text only appears after JavaScript runs: crawlers that do not run it "
                           "(many AI search bots) miss it, and Googlebot reads it later"})
            if not pages:
                checks += webpage.robots_audit(webpage.robots_info(final))
            links = content_links(items, final)
            record = {
                "id": pid, "url": url, "final_url": final, "copied": datetime.datetime.now().isoformat(timespec="seconds"),
                "rendered_with": "browser" if rendered else "no JavaScript",
                "meta": {k: meta[k] for k in ("title", "description", "canonical", "lang")},
                "breadcrumbs": webpage.breadcrumbs_from(source_html, final),
                "removed_empty_sections": removed, "audit": checks,
                "claims": webpage.claim_flags("\n".join(b["text"] for b in blocks)),
                "outline": [{"level": b["level"], "text": b["text"]} if b["kind"] == "heading"
                            else {"level": 0, "text": b["text"], "pseudo": True}
                            for b in blocks if b["kind"] == "heading" or b.get("pseudo")],
                "words_raw": raw_words, "words_rendered": words_js, "links": links,
            }
            webpage.write_copy(pg["original_md"], {"source": url, "final_url": final, "copied": record["copied"],
                                                   "note": "Snapshot of the page as copied. Do not edit: edit page.md"},
                               webpage.blocks_to_md(blocks, final))
            pg["original_json"].write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
            if replace or not pg["copy"].is_file():
                webpage.write_copy(pg["copy"], {"title": meta.get("title", ""), "description": meta.get("description", ""),
                                                "url": meta.get("canonical") or final, "lang": meta.get("lang") or "en",
                                                "copied_from": final, "copied": record["copied"][:10]},
                                   webpage.items_to_md(items, final))
            pages.append({"id": pid, "url": url, "final_url": final, "title": meta.get("title", ""),
                          "h1": next((i["text"] for i in items if i["kind"] == "h1"), pid),
                          "depth": depth if depth != 9 else None, "parent": parent,
                          "words_raw": raw_words, "words_rendered": words_js})
            log(f"  saved as {pid}: {words_js} words with JavaScript, {raw_words} without")
            if depth < 2:
                for link in links:
                    if link.startswith(prefix) and link not in seen:
                        queue.append((link, depth + 1, pid))
            time.sleep(1)  # be gentle with the site
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pages:
        raise ValueError("No page could be copied.")
    site = {"start": start, "prefix": prefix, "copied": datetime.datetime.now().isoformat(timespec="seconds"),
            "browser": bool(browser), "pages": pages}
    old = load_map(p)
    if old and not replace:  # keep pages copied earlier that this run did not reach
        ids = {x["id"] for x in pages}
        site["pages"] += [x for x in old["pages"] if x["id"] not in ids and page_paths(p, x["id"])["copy"].is_file()]
    save_map(p, site)
    _migrate_single_copy(p, site)
    render_site(p)
    return site


def _migrate_single_copy(p, site):
    """An edited single-page copy from the earlier Web page tab (webpage/page.md)
    becomes the copy of the matching page of the site."""
    folder = paths(p)["folder"]
    old = folder / "page.md"
    if not old.is_file():
        return
    meta, old_body = webpage.read_copy(old)
    edited = True
    if (folder / "original.md").is_file() and (folder / "original.json").is_file():
        _, old_original = webpage.read_copy(folder / "original.md")
        removed = json.loads((folder / "original.json").read_text(encoding="utf-8")).get("removed_empty_sections", [])
        edited = not webpage.changes(old_original, removed, old_body, set())["same"]
    target = norm_url(meta.get("copied_from") or meta.get("url") or "")
    for pg in site["pages"]:
        if edited and target and target == pg["final_url"]:  # an unedited old copy is not kept:
            shutil.copyfile(old, page_paths(p, pg["id"])["copy"])  # the new one has the JavaScript text too
            break
    for name in ("page.md", "original.md", "original.json", "rebuilt.html"):
        (folder / name).unlink(missing_ok=True)


def import_page(p, url, raw_html, filename=""):
    """Add or refresh one page from an HTML file saved in the browser (when the
    site blocks automatic downloads)."""
    why = webpage.fetch_sources.block_reason(raw_html)
    if why:
        raise ValueError(f"That file is a {why}, not the page. Save the page again once it shows.")
    site = load_map(p) or {"start": norm_url(url), "prefix": norm_url(url), "pages": [], "browser": False}
    meta, blocks = webpage.parse_page(raw_html)
    final = norm_url(meta.get("canonical") or url)
    if not final.startswith("http"):
        raise ValueError("Give the page's address too, so Atlas knows which page this is.")
    items, removed = webpage.structure(blocks)
    existing = next((x for x in site["pages"] if x["final_url"] == final), None)
    pid = existing["id"] if existing else page_id(final, {x["id"] for x in site["pages"]})
    pg = page_paths(p, pid)
    pg["dir"].mkdir(parents=True, exist_ok=True)
    words = len(webpage.words_of(blocks))
    record = {"id": pid, "url": url, "final_url": final, "copied": datetime.datetime.now().isoformat(timespec="seconds"),
              "rendered_with": f"imported file {filename}", "meta": {k: meta[k] for k in ("title", "description", "canonical", "lang")},
              "breadcrumbs": webpage.breadcrumbs_from(raw_html, final), "removed_empty_sections": removed,
              "audit": [c for c in webpage.audit(meta, blocks) if c["check"] != "Server"],
              "claims": webpage.claim_flags("\n".join(b["text"] for b in blocks)),
              "outline": [{"level": b["level"], "text": b["text"]} for b in blocks if b["kind"] == "heading"],
              "words_raw": None, "words_rendered": words, "links": content_links(items, final)}
    webpage.write_copy(pg["original_md"], {"source": url, "final_url": final, "copied": record["copied"],
                                           "note": "Snapshot of the page as imported. Do not edit: edit page.md"},
                       webpage.blocks_to_md(blocks, final))
    pg["original_json"].write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    if not pg["copy"].is_file():
        webpage.write_copy(pg["copy"], {"title": meta.get("title", ""), "description": meta.get("description", ""),
                                        "url": final, "lang": meta.get("lang") or "en", "copied_from": final,
                                        "copied": record["copied"][:10]}, webpage.items_to_md(items, final))
    if not existing:
        site["pages"].append({"id": pid, "url": url, "final_url": final, "title": meta.get("title", ""),
                              "h1": next((i["text"] for i in items if i["kind"] == "h1"), pid),
                              "depth": None, "parent": None, "words_raw": None, "words_rendered": words})
    save_map(p, site)
    render_site(p)
    return pid


# --- the mini website ----------------------------------------------------------------------
SITE_CSS = """*{box-sizing:border-box}
body{margin:0;font:16px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;color:#303030;background:#fff}
a{color:#e2000f;text-decoration:none} a:hover{text-decoration:underline}
.dh{border-bottom:1px solid #e5e5e5;background:#fff;position:sticky;top:0;z-index:2}
.dh .bar{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:28px;padding:14px 20px}
.dh .logo{font:800 26px/1 Arial,sans-serif;color:#e2000f;letter-spacing:-.5px}
.dh nav{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:14px}
.dh nav a{color:#303030;padding:4px 0;border-bottom:2px solid transparent}
.dh nav a.on,.dh nav a:hover{border-bottom-color:#e2000f;text-decoration:none}
main{max-width:1180px;margin:0 auto;padding:0 20px 40px}
.crumbs{font-size:13px;color:#707070;padding:14px 0 4px}
.crumbs a{color:#707070} .crumbs span{margin:0 6px}
h1{font-size:2.4rem;line-height:1.15;margin:.3em 0 .4em;color:#303030;font-weight:700}
article>h1+p,article>h1+nav+p{font-size:1.15rem;color:#505050;max-width:900px}
h2{font-size:1.7rem;margin:1.8em 0 .5em;padding-top:.6em;border-top:1px solid #e5e5e5}
h3{font-size:1.2rem;margin:1.3em 0 .4em}
article{max-width:1180px} article>p,article>ul,article>table{max-width:900px}
nav.toc{background:#f4f4f4;padding:12px 18px;margin:16px 0;font-size:.95rem;max-width:900px}
nav.toc ol{margin:6px 0 0;padding-left:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px;margin:14px 0 24px}
.card{display:flex;flex-direction:column;border:1px solid #e5e5e5;padding:18px;color:#303030;background:#fff;min-height:100%}
.card:hover{border-color:#e2000f;text-decoration:none;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.card h3{margin:0 0 8px;font-size:1.1rem;color:#303030}
.card p{margin:0 0 12px;font-size:.93rem;color:#505050;flex:1}
.card .more{color:#e2000f;font-weight:600;font-size:.9rem}
.card .more::after{content:" \\203A"}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.95rem}
th,td{border:1px solid #e5e5e5;padding:7px 9px;text-align:left;vertical-align:top} th{background:#f4f4f4}
footer{background:#303030;color:#d0d0d0;margin-top:30px}
footer .in{max-width:1180px;margin:0 auto;padding:22px 20px;font-size:13px}
footer a{color:#fff} footer .updated{max-width:1180px;margin:0 auto;padding:0 20px 18px;font-size:12px;color:#a0a0a0}
@media(max-width:640px){h1{font-size:1.8rem}.dh .bar{flex-wrap:wrap;gap:10px}}"""


# --- wiki blocks: product facts that follow the wiki ---------------------------------------
# A line "{{wiki: platforms/heat-pump-platforms}}" (or "...#Section") in a page copy is
# replaced, every time the website is built, by that wiki concept as it is now. When
# the team changes the wiki, the web page changes with it.
WIKI_RE = re.compile(r"^[ \t]*\{\{\s*wiki:\s*([^}#]+?)\s*(?:#\s*([^}]+?))?\s*\}\}[ \t]*$", re.M)
NOT_WEB_TYPES = {"policy", "reference", "test parameter", "guideline", "website"}
GENERIC_HEADINGS = {"facts", "summary", "rule", "rules", "what it is"}
INTERNAL_NOTE_RE = re.compile(r"never claim|brochure gives no|in our sources|^all figures from|^see [a-z ]+\.?$"
                              r"|are described in|not published in the brochure|; see ", re.I)


def wiki_root(p):
    return products.wiki_dir(p)


def wiki_blocks(p):
    """The wiki concepts a page can include: [{ref, title, type, sections}]."""
    root = wiki_root(p)
    if not root.is_dir():
        return []
    out = []
    for f in sorted(root.rglob("*.md")):
        if f.name in ("index.md", "log.md"):
            continue
        fm, body = webpage.read_copy(f)
        if str(fm.get("type", "")).lower() in NOT_WEB_TYPES:
            continue
        out.append({"ref": f.relative_to(root).with_suffix("").as_posix(), "title": fm.get("title", f.stem),
                    "type": fm.get("type", ""), "sections": re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", body)})
    return out


def wiki_block(p, ref, section=None):
    """Markdown of one wiki concept (or one of its sections) for a web page:
    footnotes and links to other concepts removed, headings one level below the
    page's sections, internal notes (never-claim remarks) left out."""
    root = wiki_root(p).resolve()
    f = (root / (ref if ref.endswith(".md") else ref + ".md")).resolve()
    if root not in f.parents or not f.is_file():
        return None
    _, body = webpage.read_copy(f)
    body = re.sub(r"(?m)^\[\^[^\]]+\]:.*\n?", "", body)
    body = re.sub(r"\[\^[^\]]+\]", "", body)
    body = re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]*\)", r"\1", body)
    lines = body.splitlines()
    if section:
        start = next((i for i, l in enumerate(lines)
                      if re.match(r"^(#{1,6})\s+" + re.escape(section.strip()) + r"\s*$", l, re.I)), None)
        if start is None:
            return None
        lvl = len(re.match(r"^(#+)", lines[start]).group(1))
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^#{1,%d}\s" % lvl, lines[i])), len(lines))
        lines = lines[start + 1:end]
    out = []
    for l in lines:
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", l)
        if m:
            if m.group(2).strip().lower() in GENERIC_HEADINGS:
                continue
            out.append("### " + m.group(2))
        elif INTERNAL_NOTE_RE.search(l.strip().lstrip("-* ")):
            continue
        else:
            out.append(re.sub(r"^Only verifiable points:\s*", "", l.rstrip()))
    kept = []  # drop headings left with nothing under them
    for i, l in enumerate(out):
        if l.startswith("### "):
            nxt = next((x for x in out[i + 1:] if x.strip()), "")
            if not nxt or nxt.startswith("### "):
                continue
        kept.append(l)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def expand_wiki(p, md):
    """(Markdown with every {{wiki: ...}} line replaced, refs used, refs not found)."""
    used, missing = [], []

    def repl(m):
        ref, section = m.group(1).strip(), m.group(2)
        block = wiki_block(p, ref, section)
        key = ref + (f"#{section.strip()}" if section else "")
        if block is None:
            missing.append(key)
            return ""
        used.append(key)
        return "\n" + block + "\n"
    return WIKI_RE.sub(repl, md), used, missing


# --- training against the competitors ------------------------------------------------------
QUESTION_WORDS = set("""what which who how why when where whose is are do does can could should would
best good better most recommend recommended choose use used need needs make makes made give gives
offer offers help helps work works find get buy pick select brand brands supplier suppliers
manufacturer manufacturers company companies product products type types kind""".split())


def competitor_gaps(p, md, competitors, questions):
    """For each buyer question: where this page ranks against the competitor pages
    (whole page and best passage), which page wins, the question's words the
    winner has and this page lacks, and the wiki concepts that hold those words.
    This is how the page is trained: add the wiki block, not the competitor's text."""
    lab = webpage.lab
    page = webpage._Page("this page", "Danfoss", md)
    mine = set(lab.tokens(md))
    concepts = []
    for b in wiki_blocks(p):
        text = wiki_block(p, b["ref"]) or ""
        concepts.append((b, set(lab.tokens(b["title"] + " " + text))))
    rows = []
    for q in questions:
        corpus = competitors + [page]
        pr = lab.PassageRanker(corpus)
        ranked = pr.rank(q)
        prank = next(i for i, (_, d) in enumerate(ranked) if d is page) + 1
        whole = lab.BM25(corpus).rank(q)
        wrank = next(i for i, (_, d) in enumerate(whole) if d is page) + 1
        winner = next((d for _, d in ranked if d is not page), None)
        qterms = [t for t in dict.fromkeys(lab.tokens(q)) if t not in QUESTION_WORDS and len(t) > 2]
        theirs = set(lab.tokens(getattr(winner, "full_text", "") or winner.text)) if winner else set()
        missing = [t for t in qterms if t not in mine and t in theirs]
        absent = [t for t in qterms if t not in mine and t not in theirs]
        suggest = []
        for t in missing + absent:
            for b, toks in concepts:
                if t in toks and b["ref"] not in [s["ref"] for s in suggest]:
                    suggest.append({"ref": b["ref"], "title": b["title"], "term": t})
        rows.append({"question": q, "passage_rank": prank, "page_rank": wrank, "pages": len(corpus),
                     "winner": f"{winner.brand} ({winner.name})" if winner and prank > 1 else "",
                     "missing": missing, "absent_everywhere": absent, "wiki": suggest[:4]})
    rows.sort(key=lambda r: (-r["passage_rank"], -len(r["missing"])))
    return rows


def _copy_items(p, pid):
    meta, body = webpage.read_copy(page_paths(p, pid)["copy"])
    body, _, _ = expand_wiki(p, body)
    return meta, webpage.md_to_items(body)


def render_site(p):
    """Every page copy as a static HTML page of the mini website, with links
    between the pages pointing to each other, then the sitemap."""
    site = load_map(p)
    if not site:
        return
    by_url = {}
    for pg in site["pages"]:
        meta, _ = webpage.read_copy(page_paths(p, pg["id"])["copy"])
        for u in (pg["final_url"], pg["url"], meta.get("url", "")):
            if u:
                by_url[norm_url(u)] = pg["id"]
    hub = site["pages"][0]
    top = [hub] + [x for x in site["pages"] if x.get("parent") == hub["id"]][:9]

    def link_map(u):
        pid = by_url.get(norm_url(u))
        return f"{pid}.html" if pid else None

    for pg in site["pages"]:
        meta, items = _copy_items(p, pg["id"])
        rec = json.loads(page_paths(p, pg["id"])["original_json"].read_text(encoding="utf-8"))
        nav = "".join(f'<a href="{x["id"]}.html" class="{"on" if x["id"] == pg["id"] else ""}">'
                      f'{html.escape(_short(x["h1"]))}</a>' for x in top)
        crumbs = [(n, u) for n, u in rec.get("breadcrumbs", [])]
        trail = " <span>›</span> ".join(
            (f'<a href="{link_map(u) or html.escape(u)}">{html.escape(n)}</a>') for n, u in crumbs[:-1])
        trail_html = f'<div class="crumbs">{trail} <span>›</span> {html.escape(pg["h1"])}</div>' if crumbs else ""
        chrome = {
            "css": SITE_CSS,
            "header": f'<header class="dh"><div class="bar"><a class="logo" href="{hub["id"]}.html">Danfoss</a>'
                      f'<nav aria-label="Catalog">{nav}</nav></div></header>',
            "crumbs": trail_html,
            "footer": '<div class="in">Danfoss A/S · Nordborgvej 81, 6430 Nordborg, Denmark</div>',
        }
        page_html = webpage.render_html(
            items, {"title": meta.get("title", ""), "description": meta.get("description", "")},
            meta.get("url") or pg["final_url"], [tuple(b) for b in crumbs], meta.get("lang") or "en",
            note=f"Atlas reconstruction of {pg['final_url']} for testing. Not the official Danfoss website.",
            link_map=link_map, chrome=chrome)
        page_paths(p, pg["id"])["html"].write_text(page_html, encoding="utf-8")
    webpage.write_sitemap(p)


def _short(s, n=34):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


# --- how the site spreads authority -------------------------------------------------------
def site_checks(p):
    """Structure checks of the copied site (your copies) and of Danfoss's pages
    (snapshots): click depth from the first page, links between pages, orphan
    pages, sitemap, and how much text a crawler without JavaScript gets."""
    site = load_map(p)
    if not site:
        return None
    ids = [x["id"] for x in site["pages"]]
    by_url, out_links = {}, {}
    for pg in site["pages"]:
        meta, items = _copy_items(p, pg["id"])
        for u in (pg["final_url"], pg["url"], meta.get("url", "")):
            if u:
                by_url[norm_url(u)] = pg["id"]
    for pg in site["pages"]:
        meta, items = _copy_items(p, pg["id"])
        out_links[pg["id"]] = sorted({by_url[u] for u in content_links(items, pg["final_url"])
                                      if u in by_url and by_url[u] != pg["id"]})
    incoming = {i: [a for a in ids if i in out_links[a]] for i in ids}
    depth = {ids[0]: 0}  # click depth from the first page, following your copies' links
    frontier = [ids[0]]
    while frontier:
        nxt = []
        for a in frontier:
            for b in out_links[a]:
                if b not in depth:
                    depth[b] = depth[a] + 1
                    nxt.append(b)
        frontier = nxt
    sitemap = paths(p)["sitemap"].read_text(encoding="utf-8") if paths(p)["sitemap"].is_file() else ""
    rows = []
    for pg in site["pages"]:
        meta, items = _copy_items(p, pg["id"])
        loc = meta.get("url") or pg["final_url"]
        rows.append({
            "id": pg["id"], "h1": next((i["text"] for i in items if i["kind"] == "h1"), pg["h1"]),
            "url": loc, "depth": depth.get(pg["id"]), "links_out": len(out_links[pg["id"]]),
            "links_in": len(incoming[pg["id"]]), "in_sitemap": html.escape(loc) in sitemap,
            "words": len(webpage.words_of(items)), "words_raw_original": pg.get("words_raw"),
            "words_rendered_original": pg.get("words_rendered"),
        })
    orphans = [r["id"] for r in rows[1:] if r["links_in"] == 0]
    deep = [r["id"] for r in rows if r["depth"] is not None and r["depth"] > 3]
    unreached = [r["id"] for r in rows if r["depth"] is None]
    js_only = [r["id"] for r in rows if r["words_raw_original"] is not None and r["words_rendered_original"]
               and r["words_raw_original"] < 0.5 * r["words_rendered_original"]]
    summary = [
        {"check": "Pages in the mini website", "value": len(rows), "status": "ok"},
        {"check": "Pages a crawler cannot reach from the first page", "value": len(unreached),
         "status": "ok" if not unreached else "bad", "note": ", ".join(unreached)},
        {"check": "Orphan pages (no page links to them)", "value": len(orphans),
         "status": "ok" if not orphans else "bad", "note": ", ".join(orphans)},
        {"check": "Pages more than 3 clicks deep", "value": len(deep), "status": "ok" if not deep else "warn",
         "note": ", ".join(deep)},
        {"check": "Pages in sitemap.xml", "value": f"{sum(r['in_sitemap'] for r in rows)} of {len(rows)}",
         "status": "ok" if all(r["in_sitemap"] for r in rows) else "warn"},
        {"check": "Danfoss pages whose text needs JavaScript", "value": len(js_only),
         "status": "ok" if not js_only else "bad", "note": ", ".join(js_only) + (
             " — in your copies all text is in the HTML" if js_only else "")},
    ]
    return {"summary": summary, "pages": rows}


# --- one page -------------------------------------------------------------------------------
def lab_page(p, danfoss_url):
    """The page that represents the product in the citation lab: the product's own
    Danfoss page if it is in the site, else the first page."""
    site = load_map(p)
    if not site:
        return None
    want = {norm_url(danfoss_url)} if danfoss_url else set()
    for pg in site["pages"]:
        if want & {pg["url"], pg["final_url"]}:
            return pg["id"]
    return site["pages"][0]["id"]


def page_analysis(p, pid, questions, competitors, allowed_numbers, lab_id, top_k=5):
    site = load_map(p)
    pg = next((x for x in site["pages"] if x["id"] == pid), None) if site else None
    if not pg:
        raise ValueError(f"No page '{pid}' in the copied site")
    pth = page_paths(p, pid)
    rec = json.loads(pth["original_json"].read_text(encoding="utf-8"))
    _, original_md = webpage.read_copy(pth["original_md"])
    copy_text = pth["copy"].read_text(encoding="utf-8")
    cmeta, copy_md = webpage.read_copy_text(copy_text)
    copy_md, blocks_used, blocks_missing = expand_wiki(p, copy_md)
    items = webpage.md_to_items(copy_md)
    ch = webpage.changes(original_md, rec.get("removed_empty_sections", []), copy_md, allowed_numbers)
    page_html = pth["html"].read_text(encoding="utf-8") if pth["html"].is_file() else ""
    rmeta, _ = webpage.parse_page(page_html)
    page_url = cmeta.get("url") or pg["final_url"]
    sitemap = paths(p)["sitemap"].read_text(encoding="utf-8") if paths(p)["sitemap"].is_file() else ""
    copy_audit = webpage.audit(rmeta, items, None, items)
    copy_audit.append({"check": "Listed in sitemap.xml", "value": "yes" if html.escape(page_url) in sitemap else "no",
                       "status": "ok" if html.escape(page_url) in sitemap else "warn"})
    md_before, md_after = webpage.md_for_crawler(original_md), webpage.to_markdown(items)
    lab_file = write_lab(p, pid, ch["same"]) if pid == lab_id and page_html else None
    return {
        "id": pid, "copy": {"text": copy_text, "copied": rec["copied"], "final_url": pg["final_url"],
                            "rendered_with": rec.get("rendered_with", ""),
                            "changed": datetime.datetime.fromtimestamp(pth["copy"].stat().st_mtime).isoformat(timespec="seconds")},
        "changes": ch, "lab_file": lab_file, "is_lab_page": pid == lab_id,
        "audit": {"original": rec["audit"], "rebuilt": copy_audit},
        "claims": {"original": rec["claims"], "copy": webpage.claim_flags(webpage.strip_links(copy_md))},
        "googlebot": {"original": webpage.googlebot_view(md_before, questions),
                      "rebuilt": webpage.googlebot_view(md_after, questions)},
        "bm25": webpage.bm25_table({"original": md_before, "rebuilt": md_after}, competitors, questions, top_k),
        "outline": {"original": rec["outline"],
                    "rebuilt": [{"level": int(i["kind"][1]), "text": i["text"]}
                                for i in items if i["kind"] in ("h1", "h2", "h3")]},
        "file": f"site/{pid}.html",
        "wiki": {"used": blocks_used, "missing": blocks_missing},
        "gaps": competitor_gaps(p, webpage.to_markdown(items), competitors, questions),
    }


def write_lab(p, pid, same=None):
    """The product's page as the citation lab reads it (style 'restructured'),
    extracted from the rendered page the same way as Danfoss's page."""
    pth = page_paths(p, pid)
    if not pth["html"].is_file():
        return None
    if same is None:
        _, original_md = webpage.read_copy(pth["original_md"])
        rec = json.loads(pth["original_json"].read_text(encoding="utf-8"))
        _, body = webpage.read_copy(pth["copy"])
        body, _, _ = expand_wiki(p, body)
        same = webpage.changes(original_md, rec.get("removed_empty_sections", []), body, set())["same"]
    meta, _ = webpage.read_copy(pth["copy"])
    lab = webpage.lab_file(webpage.lab_text(pth["html"].read_text(encoding="utf-8")),
                           meta.get("url") or "").replace(
        "style: restructured\n",
        f"style: restructured\ncontent: {'same as the original' if same else 'changed'}\n")
    paths(p)["lab"].parent.mkdir(parents=True, exist_ok=True)
    paths(p)["lab"].write_text(lab, encoding="utf-8")
    return paths(p)["lab"].relative_to(REPO).as_posix()


def refresh(p, danfoss_url):
    """Rebuild the website and the lab copy from the copies and the wiki as they are
    now: a change in the wiki reaches the web pages and the citation test."""
    if not load_map(p):
        return False
    render_site(p)
    pid = lab_page(p, danfoss_url)
    if pid:
        write_lab(p, pid)
    return True


def save_page(p, pid, text):
    pth = page_paths(p, pid)
    if not pth["original_json"].is_file():
        raise ValueError(f"No page '{pid}' in the copied site")
    _, body = webpage.read_copy_text(text)
    expanded, _, missing = expand_wiki(p, body)
    if missing:
        raise ValueError("These wiki blocks do not exist: " + ", ".join(missing)
                         + ". Pick them from the list under the editor.")
    if not any(x["kind"] == "h1" for x in webpage.md_to_items(expanded)):
        raise ValueError("The page needs one main title: a line starting with '# '.")
    pth["copy"].write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    render_site(p)  # titles in the menu and links between pages may have changed
