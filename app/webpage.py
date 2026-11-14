"""
Web page tools for the Atlas app's "Web page" and "Model by model" tabs.

  fetch()          download a page the way a crawler does (no JavaScript), timing it
  parse_page()     the page's content blocks (headings, paragraphs, list items, tables)
  rebuild()        the same content, re-laid out for BM25 and Googlebot: FORMAT ONLY
  content_check()  proof that the rebuilt page holds exactly the same words and numbers
  audit()          crawler checks: status, redirects, speed, metadata, headings, JSON-LD
  googlebot_view() the text a crawler reads, cut into passages like AI search does
  bm25_table()     per question: page rank and best passage, original vs rebuilt

Standard library only. Ranking and passages come from lab/experiment.py, so the
numbers match the citation lab exactly.
"""
import datetime
import html
import html.parser
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO / "lab"))
import experiment as lab  # noqa: E402  (BM25, tokens, passages: same as the lab)
import fetch_sources  # noqa: E402  (the lab's text extractor, for the lab copy)

UA = fetch_sources.UA
SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "button", "form",
        "nav", "header", "footer", "aside", "select", "option", "dialog"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "base", "embed", "track"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCKS = {"p", "li", "td", "th", "dt", "dd", "figcaption", "blockquote", "caption", "div",
          "section", "article", "summary", "label"} | HEADINGS
CHROME_CLASS = re.compile(r"breadcrumb|cookie|consent|skip-link|sr-only|visually-hidden", re.I)
NUM_RE = re.compile(r"\d[\d.,]*\d|\d")
BLOCK_HELP = ("Its bot protection stopped the download. Your saved copy is kept and still works. "
              "Try again later, or save the page from your browser (Ctrl+S, 'Webpage, HTML only') "
              "and import that file.")


# --- fetching -------------------------------------------------------------------
class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"status": code, "from": req.full_url,
                           "to": urllib.parse.urljoin(req.full_url, newurl)})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, timeout=30):
    """The raw HTML, as a crawler that does not run JavaScript gets it, with
    status, redirects and timing. Raises ValueError with a readable message."""
    red = _Redirects()
    opener = urllib.request.build_opener(red)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            ttfb = time.perf_counter() - t0  # headers received
            data = resp.read()
            total = time.perf_counter() - t0
            status, final = resp.status, resp.geturl()
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        why = fetch_sources.block_reason(e.read().decode("utf-8", errors="replace"), e.code)
        raise ValueError(f"The site answered with a {why} instead of the page ({url}). " + BLOCK_HELP
                         if why else f"The page answered with error {e.code} ({url})")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ValueError(f"Could not download {url}: {getattr(e, 'reason', e)}")
    ctype = headers.get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ctype)
    text = data.decode(m.group(1) if m else "utf-8", errors="replace")
    why = fetch_sources.block_reason(text, status)
    if why:
        raise ValueError(f"The site answered with a {why} instead of the page ({url}). " + BLOCK_HELP)
    return {"url": url, "final_url": final, "status": status, "redirects": red.chain,
            "ttfb": round(ttfb, 3), "total": round(total, 3), "bytes": len(data),
            "x_robots": headers.get("x-robots-tag", ""), "content_type": ctype,
            "fetched": datetime.datetime.now().isoformat(timespec="seconds"), "html": text}


# --- parsing --------------------------------------------------------------------
def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


class _Parser(html.parser.HTMLParser):
    """Collects the head metadata and the content blocks of <main> (or <body>).
    A block is one heading, paragraph, list item, table row or bare text in a div.
    A paragraph whose only text is bold is marked as a 'pseudo' heading: it looks
    like a heading to a reader, but a crawler sees a paragraph."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {"title": "", "description": "", "robots": "", "canonical": "", "lang": "",
                     "hreflang": 0, "jsonld": [], "scripts": 0, "ext_scripts": 0,
                     "images": 0, "images_no_alt": 0, "has_main": False}
        self.stack = []        # open tags: (tag, skipping, chrome)
        self.blocks = []       # dicts: kind, text, level, list, href
        self.cur = None        # block being filled
        self.in_title = self.in_jsonld = False
        self.jsonld_buf = []
        self.main_depth = None
        self.list_id = 0
        self.lists = []        # stack of list ids
        self.row = None        # table row cells
        self.bold_only = None  # for pseudo-headings: text inside <strong>/<b> vs outside
        self.a_hrefs = []      # hrefs of the open <a> tags

    # skipping and chrome
    def _skipping(self):
        return any(s for _, s, _ in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.meta["lang"] = a.get("lang", "")
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            if name == "description":
                self.meta["description"] = clean(a.get("content"))
            elif name in ("robots", "googlebot"):
                self.meta["robots"] = (self.meta["robots"] + " " + (a.get("content") or "")).strip()
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.meta["canonical"] = a.get("href", "")
            elif rel == "alternate" and a.get("hreflang"):
                self.meta["hreflang"] += 1
        elif tag == "title" and not self.meta["title"]:
            self.in_title = True
        elif tag == "script":
            self.meta["scripts"] += 1
            if a.get("src"):
                self.meta["ext_scripts"] += 1
            if (a.get("type") or "").lower() == "application/ld+json":
                self.in_jsonld, self.jsonld_buf = True, []
        elif tag == "img" and self._in_content():
            self.meta["images"] += 1
            if not (a.get("alt") or "").strip():
                self.meta["images_no_alt"] += 1
        if tag == "a":
            self.a_hrefs.append(a.get("href") or "")
        if tag in VOID:
            if tag == "br" and self.cur is not None:
                self.cur["text"] += " "
            return
        if tag == "main":
            self.meta["has_main"] = True
            self.main_depth = len(self.stack)
        chrome = bool(CHROME_CLASS.search(a.get("class") or "") or a.get("aria-hidden") == "true"
                      or "hidden" in a)
        self.stack.append((tag, tag in SKIP or chrome, chrome))
        if self._skipping():
            return
        if tag in ("ul", "ol"):
            self.list_id += 1
            self.lists.append(self.list_id)
        elif tag == "tr":
            self.row = []
        elif tag in ("strong", "b") and self.cur is not None and self.bold_only is not None:
            self.bold_only["depth"] += 1
        elif tag == "a" and self.cur is not None:
            self.cur.setdefault("_href", a.get("href", ""))
        if tag in BLOCKS and self._inside_item(exclude_last=True) and tag not in ("li", "td", "th"):
            return  # a <p> or <div> inside a list item or cell is part of that item
        if tag in BLOCKS:
            self._close_block()
            if tag in ("td", "th") and self.row is not None:
                self.cur = {"kind": "cell", "text": ""}
            else:
                kind = "heading" if tag in HEADINGS else ("li" if tag == "li" else "p" if tag == "p" else "text")
                self.cur = {"kind": kind, "tag": tag, "text": "",
                            "level": int(tag[1]) if tag in HEADINGS else None,
                            "list": self.lists[-1] if tag == "li" and self.lists else None}
                href = self._open_link()
                if href:
                    self.cur["_href"] = href
            self.bold_only = {"depth": 0, "bold": "", "plain": ""}

    def handle_endtag(self, tag):
        if tag == "a" and self.a_hrefs:
            self.a_hrefs.pop()
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_jsonld:
            self.in_jsonld = False
            raw = "".join(self.jsonld_buf).strip()
            try:
                self.meta["jsonld"].append(json.loads(raw))
            except ValueError:
                self.meta["jsonld"].append({"_invalid": raw[:200]})
        if not any(t == tag for t, _, _ in self.stack):
            return
        skipping_before = self._skipping()
        while self.stack:
            t, _, _ = self.stack.pop()
            if t == tag:
                break
        if skipping_before and not self._skipping():
            return
        if self._skipping():
            return
        if tag in BLOCKS and tag not in ("li", "td", "th") and self._inside_item():
            return  # end of a <p>/<div> inside a list item or cell: the item goes on
        if tag == "main":
            self._close_block()
            self.main_depth = None
        if tag in ("ul", "ol") and self.lists:
            self._close_block()
            self.lists.pop()
        elif tag in ("strong", "b") and self.bold_only and self.bold_only["depth"]:
            self.bold_only["depth"] -= 1
        elif tag in ("td", "th") and self.row is not None:
            if self.cur is not None and self.cur.get("kind") == "cell":
                self.row.append(clean(self.cur["text"]))
                self.cur = None
        elif tag == "tr" and self.row is not None:
            self._close_block()
            if any(self.row):
                self.blocks.append({"kind": "row", "text": " | ".join(self.row), "cells": self.row,
                                    "in_main": self._in_main()})
            self.row = None
        elif tag in BLOCKS:
            self._close_block()

    def handle_data(self, data):
        if self.in_title:
            self.meta["title"] += data
            return
        if self.in_jsonld:
            self.jsonld_buf.append(data)
            return
        if self._skipping() or self.cur is None:
            if not self._skipping() and data.strip() and self._in_content():
                # text directly inside a container: treat as its own text block
                href = self._open_link()
                self.cur = {"kind": "p" if href else "text", "tag": "div", "text": "",
                            "level": None, "list": None}
                if href:
                    self.cur["_href"] = href
                self.bold_only = {"depth": 0, "bold": "", "plain": ""}
            else:
                return
        self.cur["text"] += data
        if self.bold_only is not None and data.strip():
            key = "bold" if self.bold_only["depth"] else "plain"
            self.bold_only[key] += data

    def _in_main(self):
        return self.main_depth is not None

    def _inside_item(self, exclude_last=False):
        """Inside an open <li>, <td> or <th> (that is not a nested list)."""
        stack = self.stack[:-1] if exclude_last else self.stack
        for t, _, _ in reversed(stack):
            if t in ("li", "td", "th"):
                return True
            if t in ("ul", "ol", "table"):
                return False
        return False

    def _open_link(self):
        return self.a_hrefs[-1] if self.a_hrefs else None

    def _in_content(self):
        return self._in_main() or not self.meta["has_main"]

    def _close_block(self):
        b, self.cur = self.cur, None
        if b is None or b.get("kind") == "cell":
            if b is not None and self.row is not None:
                self.row.append(clean(b["text"]))
            return
        text = clean(b["text"])
        if not text:
            return
        b["text"] = text
        bo = self.bold_only or {}
        b["pseudo"] = (b["kind"] in ("p", "text") and bool(bo.get("bold", "").strip())
                       and not bo.get("plain", "").strip() and len(text) <= 90
                       and not text.endswith((".", "!", "?")))
        b["in_main"] = self._in_main()
        if b.get("_href"):
            b["href"] = b.pop("_href")
        self.blocks.append(b)
        self.bold_only = None


def parse_page(raw_html):
    """(meta, blocks). Blocks are those in <main> if the page has one."""
    p = _Parser()
    p.feed(raw_html)
    p.close()
    p.meta["title"] = clean(p.meta["title"])
    blocks = [b for b in p.blocks if b.get("in_main")] if p.meta["has_main"] else p.blocks
    # drop exact repeats of the block just before (e.g. a title repeated in a caption)
    out = []
    for b in blocks:
        if out and b["text"] == out[-1]["text"] and b["kind"] != "li":
            continue
        out.append(b)
    return p.meta, out


# --- the format-only rebuild -------------------------------------------------------
def _is_card(blocks, i):
    """A catalog tile: a short linked title followed by a paragraph with the same link."""
    if i + 1 >= len(blocks):
        return False
    a, b = blocks[i], blocks[i + 1]
    return (a["kind"] in ("text", "p") and a.get("href") and len(a["text"]) <= 150
            and b["kind"] in ("p", "text") and b.get("href") == a["href"] and len(b["text"]) > len(a["text"]))


def structure(blocks):
    """Turn content blocks into a clean outline, without changing any text:
      - exactly one H1 (the first H1, or the first heading)
      - real headings re-levelled: H2 for sections, H3 below, no skipped levels
      - bold-only paragraphs and lone short texts in a div become H3 headings
      - runs of short bare texts (video titles, link lists) become lists
      - headings with nothing under them are removed and reported (on this kind of
        page they are blocks a script fills in later: a crawler sees them empty)
    Returns (items, removed). Items: {kind: h1|h2|h3|p|ul|table, text|items|rows}."""
    h1_done, items, removed = False, [], []
    last_real = 1
    i, n = 0, len(blocks)
    while i < n:
        b = blocks[i]
        if b["kind"] == "heading":
            if not h1_done:
                items.append({"kind": "h1", "text": b["text"]})
                h1_done = True
            else:
                lvl = 2 if b["level"] <= 2 else 3
                if lvl == 3 and last_real < 2:
                    lvl = 2
                items.append({"kind": f"h{lvl}", "text": b["text"], "real": True})
                last_real = lvl
            i += 1
            continue
        if _is_card(blocks, i):  # catalog tiles: a linked title + a linked description
            cards = []
            while _is_card(blocks, i):
                cards.append({"title": blocks[i]["text"], "href": blocks[i]["href"],
                              "text": blocks[i + 1]["text"]})
                i += 2
            items.append({"kind": "cards", "items": cards})
            continue
        if b["kind"] == "text" and b.get("href"):  # a bare link, e.g. "Contact us"
            items.append({"kind": "p", "text": b["text"], "href": b["href"]})
            i += 1
            continue
        if b["kind"] in ("p", "text") and b.get("pseudo"):
            items.append({"kind": "h3" if last_real >= 2 else "h2", "text": b["text"], "pseudo": True})
            i += 1
            continue
        if b["kind"] == "li":
            lid, group = b.get("list"), []
            while i < n and blocks[i]["kind"] == "li" and blocks[i].get("list") == lid:
                group.append(blocks[i]["text"])
                i += 1
            items.append({"kind": "ul", "items": group})
            continue
        if b["kind"] == "row":
            rows = []
            while i < n and blocks[i]["kind"] == "row":
                rows.append(blocks[i]["cells"])
                i += 1
            items.append({"kind": "table", "rows": rows})
            continue
        if b["kind"] == "text" and len(b["text"]) <= 120 and not b["text"].endswith("."):
            run = []
            while (i < n and blocks[i]["kind"] == "text" and not blocks[i].get("pseudo")
                   and not blocks[i].get("href")
                   and len(blocks[i]["text"]) <= 120 and not blocks[i]["text"].endswith(".")):
                run.append(blocks[i]["text"])
                i += 1
            if len(run) >= 2:
                items.append({"kind": "ul", "items": run})
            else:  # one short title-like text on its own: a sub-heading
                items.append({"kind": "h3" if last_real >= 2 else "h2", "text": run[0], "pseudo": True})
            continue
        items.append({"kind": "p", "text": b["text"], "href": b.get("href")})
        i += 1
    if not h1_done and items:
        items.insert(0, {"kind": "h1", "text": items.pop(0).get("text", "")})

    # remove headings with no content before the next heading of the same or higher level
    rank = {"h1": 1, "h2": 2, "h3": 3}
    kept = []
    for j, it in enumerate(items):
        if it["kind"] in ("h2", "h3"):
            nxt = next((x for x in items[j + 1:]), None)
            if nxt is None or (nxt["kind"] in rank and rank[nxt["kind"]] <= rank[it["kind"]]):
                removed.append(it["text"])
                continue
        kept.append(it)
    return kept, removed


def _slug(s, used):
    base = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "section"
    slug, k = base, 2
    while slug in used:
        slug, k = f"{base}-{k}", k + 1
    used.add(slug)
    return slug


def _jsonld(meta, items, url, breadcrumbs, brand="Danfoss"):
    h1 = next((x["text"] for x in items if x["kind"] == "h1"), meta.get("title", ""))
    data = [{"@context": "https://schema.org", "@type": "Product", "name": h1,
             "brand": {"@type": "Brand", "name": brand},
             "description": meta.get("description") or next(
                 (x["text"] for x in items if x["kind"] == "p"), ""),
             "url": url}]
    if breadcrumbs:
        data.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                     "itemListElement": [{"@type": "ListItem", "position": k + 1, "name": name,
                                          "item": link}
                                         for k, (name, link) in enumerate(breadcrumbs)]})
    return data


def breadcrumbs_from(raw_html, base):
    """The page's breadcrumb trail with absolute links, read from the HTML links
    (not from its JSON-LD, which may be broken)."""
    m = re.search(r'<[^>]+class="[^"]*breadcrumb[^"]*"[^>]*>(.*?)</(?:ol|ul|nav)>', raw_html, re.S | re.I)
    if not m:
        return []
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', m.group(1), re.S):
        name = clean(re.sub(r"<[^>]+>", "", text))
        if name:
            out.append((name, urllib.parse.urljoin(base, html.unescape(href))))
    return out


CSS = """body{margin:0;font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1d1d1f;background:#fff}
main{max-width:820px;margin:0 auto;padding:24px 16px 16px}
footer{max-width:820px;margin:0 auto;padding:0 16px 48px}
h1{font-size:2rem;line-height:1.2;margin:.4em 0}
h2{font-size:1.45rem;margin:1.8em 0 .5em;border-top:1px solid #e3e3e0;padding-top:1em}
h3{font-size:1.15rem;margin:1.4em 0 .4em}
nav.toc{background:#f5f5f3;border-radius:10px;padding:12px 18px;margin:16px 0;font-size:.95rem}
nav.toc ol{margin:6px 0 0;padding-left:20px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.95rem}
th,td{border:1px solid #e3e3e0;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f5f5f3}
a{color:#2a6fdb}
.updated{color:#6b6b70;font-size:.9rem}"""


def render_html(items, meta, url, breadcrumbs=None, lang="en", note="", link_map=None, chrome=None):
    """A light, static HTML page: everything in the first response, no scripts
    except the JSON-LD data, one H1, a table of contents of the H2 sections.
    link_map(absolute_url) -> local href (or None) points links to pages of a
    reconstructed site; chrome = {css, header, crumbs, footer} wraps the page in
    a site's header, navigation and footer (see site.py)."""
    def href_of(target):
        absolute = urllib.parse.urljoin(url, target)
        local = link_map(absolute) if link_map else None
        return local or absolute

    def e(s):  # escaped text, with [text](url) Markdown links turned into links
        return MD_LINK_RE.sub(lambda m: f'<a href="{html.escape(href_of(m.group(2)))}">{m.group(1)}</a>',
                              html.escape(s))

    used, toc, body = set(), [], []
    for it in items:
        k = it["kind"]
        if k in ("h2", "h3"):
            sid = _slug(it["text"], used)
            it["id"] = sid
            if k == "h2":
                toc.append((sid, it["text"]))
    for it in items:
        k = it["kind"]
        if k == "h1":
            body.append(f"<h1>{e(it['text'])}</h1>")
            if len(toc) > 2:
                body.append('<nav class="toc" aria-label="Contents"><b>Contents</b><ol>'
                            + "".join(f'<li><a href="#{s}">{html.escape(t)}</a></li>' for s, t in toc)
                            + "</ol></nav>")
        elif k in ("h2", "h3"):
            body.append(f'<{k} id="{it["id"]}">{e(it["text"])}</{k}>')
        elif k == "p":
            t = e(it["text"])
            if it.get("href"):
                t = f'<a href="{html.escape(href_of(it["href"]))}">{t}</a>'
            body.append(f"<p>{t}</p>")
        elif k == "ul":
            body.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in it["items"]) + "</ul>")
        elif k == "cards":
            body.append('<div class="cards">' + "".join(
                f'<a class="card" href="{html.escape(href_of(c["href"]))}"><h3>{html.escape(c["title"])}</h3>'
                f'<p>{html.escape(c["text"])}</p><span class="more">Read more</span></a>'
                for c in it["items"]) + "</div>")
        elif k == "table":
            rows = it["rows"]
            head = rows[0] if rows else []
            body.append("<table><thead><tr>" + "".join(f"<th>{e(c)}</th>" for c in head)
                        + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>"
                                  for r in rows[1:]) + "</tbody></table>")
    ld = json.dumps(_jsonld(meta, items, url, breadcrumbs or []), ensure_ascii=False, indent=1)
    ld = ld.replace("</", "<\\/")
    title = meta.get("title") or next((x["text"] for x in items if x["kind"] == "h1"), "")
    desc = meta.get("description", "")
    today = datetime.date.today().isoformat()
    ch = chrome or {}
    return f"""<!doctype html>
<html lang="{html.escape(lang or 'en')}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{html.escape(url)}">
<script type="application/ld+json">
{ld}
</script>
<style>{ch.get("css", CSS)}</style>
</head>
<body>
{ch.get("header", "")}
<main>
{ch.get("crumbs", "")}
<article>
{chr(10).join(body)}
</article>
</main>
<footer>{ch.get("footer", "")}<p class="updated">{html.escape(note or f"Page generated {today}.")}</p></footer>
</body>
</html>
"""


# --- checks -------------------------------------------------------------------------
def words_of(items_or_blocks):
    out = []
    for it in items_or_blocks:
        if it.get("kind") == "cards":
            out += [w for c in it["items"] for w in (c["title"] + " " + c["text"]).split()]
        elif "items" in it:
            out += [w for x in it["items"] for w in x.split()]
        elif "rows" in it:
            out += [w for r in it["rows"] for c in r for w in c.split()]
        elif "cells" in it:
            out += [w for c in it["cells"] for w in c.split()]
        else:
            out += it.get("text", "").split()
    return out


def _norm_words(words):
    return [re.sub(r"[^\w%.,-]", "", w.lower()).strip(".,") for w in words if w.strip()]


def numbers(words):
    return sorted({re.sub(r"[.,]", "", n) for w in words for n in NUM_RE.findall(w)})


def content_check(blocks, items, removed):
    """Same words (as a multiset) and same numbers in the original content and
    the rebuilt content. Removed empty headings are listed, not hidden."""
    import collections
    before = collections.Counter(_norm_words(words_of(blocks)))
    removed_words = collections.Counter(_norm_words([w for t in removed for w in t.split()]))
    after = collections.Counter(_norm_words(words_of(items)))
    expected = before - removed_words
    missing = expected - after
    added = after - expected
    nb = numbers(words_of(blocks))
    na = numbers(words_of(items))
    return {"ok": not missing and not added and nb == na,
            "words_before": sum(before.values()), "words_after": sum(after.values()),
            "missing": sorted(missing.elements())[:40], "added": sorted(added.elements())[:40],
            "numbers_before": nb, "numbers_after": na, "numbers_same": nb == na,
            "removed_empty_sections": removed}


NEVER_CLAIM = [
    (r"\bthe best\b|\bnumber 1\b|\bno\.? ?1\b|\bunmatched\b|\bunparalleled\b|\boutperform\w*", "superlative"),
    (r"\bup to \d+ ?%|\d+ ?%", "percentage"),
    (r"[€$£] ?\d|\b\d+ ?(?:eur|usd|dkk)\b|\bprice[sd]?\b", "price"),
    (r"\beco[- ]?friendly\b|\benvironmentally friendly\b|\bgreen\b|\bsustainable\b|\bclimate[- ]neutral\b",
     "generic environmental claim"),
    (r"\brevolutionary\b|\bgame[- ]?changer\b|\bsuperior\b|\bhighest\b", "unsupported superlative"),
]


def claim_flags(text):
    """Sentences that break the never-claim policy (wiki/policies/never-claim.md):
    a quick rule-based screen, for a person to read, not a verdict."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = sent.strip()
        for pat, label in NEVER_CLAIM:
            m = re.search(pat, s, re.I)
            if m:
                out.append({"type": label, "match": m.group(0), "sentence": s[:220]})
                break
    return out


def audit(meta, blocks, info=None, items=None):
    """Crawler checks. Each: {check, value, status: ok|warn|bad, note}."""
    out = []

    def add(check, value, status, note=""):
        out.append({"check": check, "value": value, "status": status, "note": note})

    if info:
        add("HTTP status", info["status"], "ok" if info["status"] == 200 else "bad")
        r = info.get("redirects") or []
        add("Redirects before the page", len(r), "ok" if not r else "warn",
            " → ".join(f"{x['status']} {x['to']}" for x in r) if r else "")
        t = info["ttfb"]
        add("Time to first byte", f"{t:.2f} s", "ok" if t < 0.6 else "warn" if t < 1.5 else "bad",
            "Google: slow answers to Googlebot's requests mean fewer crawls")
        add("HTML size", f"{info['bytes'] / 1024:.0f} KB", "ok" if info["bytes"] < 300_000 else "warn")
        xr = info.get("x_robots", "")
        add("X-Robots-Tag header", xr or "none",
            "bad" if re.search(r"noindex|nosnippet", xr, re.I) else "ok")
    else:
        add("Server", "static file", "ok", "No server work: answers as fast as the host can send a file")
    add("Scripts", f"{meta['scripts']} ({meta['ext_scripts']} external)",
        "ok" if meta["scripts"] <= 5 else "warn", "Content must not depend on them")
    title = meta.get("title", "")
    add("Title", f"{len(title)} chars", "ok" if 15 <= len(title) <= 65 else "warn", title)
    d = meta.get("description", "")
    add("Meta description", f"{len(d)} chars", "ok" if 50 <= len(d) <= 160 else "warn", d)
    add("Canonical link", "yes" if meta.get("canonical") else "missing",
        "ok" if meta.get("canonical") else "warn", meta.get("canonical", ""))
    rb = meta.get("robots", "")
    add("Robots meta", rb or "none", "bad" if re.search(r"noindex|nosnippet|max-snippet:0", rb, re.I) else "ok")
    add("Language (lang)", meta.get("lang") or "missing", "ok" if meta.get("lang") else "warn")
    heads = [b for b in (items or blocks) if (b.get("kind") == "heading") or b.get("kind") in ("h1", "h2", "h3")]
    h1s = sum(1 for b in heads if b.get("level") == 1 or b.get("kind") == "h1")
    add("H1 headings", h1s, "ok" if h1s == 1 else "bad")
    if items is None:
        levels = [b["level"] for b in blocks if b["kind"] == "heading"]
        skips = sum(1 for a, b in zip(levels, levels[1:]) if b > a + 1)
        add("Skipped heading levels", skips, "ok" if not skips else "warn",
            "e.g. an H2 followed by an H4")
        pseudo = [b["text"] for b in blocks if b.get("pseudo")]
        add("Bold text used as a heading", len(pseudo), "ok" if not pseudo else "warn",
            "; ".join(pseudo[:6]))
    else:
        add("Skipped heading levels", 0, "ok")
        add("Bold text used as a heading", 0, "ok")
    words = len(words_of(items or blocks))
    add("Words readable without JavaScript", words, "ok" if words >= 300 else "warn")
    if items is None:
        _, removed = structure(blocks)
        add("Empty sections (filled by JavaScript)", len(removed), "ok" if not removed else "bad",
            "; ".join(removed) + (" — a crawler that does not run scripts sees nothing there"
                                  if removed else ""))
        seen, dups = set(), []
        for b in blocks:
            if b["kind"] == "li":
                if b["text"] in seen:
                    dups.append(b["text"])
                seen.add(b["text"])
        add("Repeated list items", len(dups), "ok" if not dups else "warn", "; ".join(dups))
    types, problems = [], []
    for j in meta.get("jsonld", []):
        for obj in (j if isinstance(j, list) else [j]):
            if "_invalid" in obj:
                problems.append("invalid JSON")
                continue
            types.append(str(obj.get("@type")))
            blob = json.dumps(obj)
            if re.search(r'"item":\s*"/[^"]*True"|"(?:item|url)":\s*"/', blob):
                problems.append(f"{obj.get('@type')}: relative or broken links")
    add("Structured data (JSON-LD)", ", ".join(types) or "none",
        "bad" if problems else ("ok" if "Product" in types else "warn"),
        "; ".join(problems) or ("" if "Product" in types else "No Product data"))
    add("Images without alt text", f"{meta['images_no_alt']} of {meta['images']}",
        "ok" if not meta["images_no_alt"] else "warn")
    return out


# --- what Googlebot sees, and BM25 ----------------------------------------------------
def to_markdown(items_or_blocks):
    """Text a crawler reads, with headings marked (#), for passages and the lab."""
    lines = []
    for it in items_or_blocks:
        k = it.get("kind")
        if k == "heading":
            lines.append("#" * min(it["level"], 6) + " " + it["text"])
        elif k in ("h1", "h2", "h3"):
            lines.append("#" * int(k[1]) + " " + it["text"])
        elif k == "ul":
            lines += [f"- {x}" for x in it["items"]]
        elif k == "cards":  # each tile is its own small section for a crawler
            for c in it["items"]:
                lines += ["### " + c["title"], c["text"]]
        elif k == "table":
            lines += [" | ".join(r) for r in it["rows"]]
        elif k == "row":
            lines.append(it["text"])
        elif k == "li":
            lines.append("- " + it["text"])
        else:
            lines.append(it.get("text", ""))
    return strip_links("\n".join(l for l in lines if l.strip()))


class _Page:
    def __init__(self, name, brand, text):
        self.name, self.brand, self.style = name, brand, name
        self.full_text = text
        self.text = " ".join(text.split()[:700])


def googlebot_view(markdown, questions, passage_words=200):
    """The passages AI search would cut from this text, and for each question the
    passage that matches it best (BM25 over this page's passages only)."""
    ps = lab.split_passages(markdown, passage_words)
    page = _Page("page", "Danfoss", markdown)
    ranker = lab.PassageRanker([page], passage_words)
    best = {}
    for q in questions:
        sc = ranker.scores(q)
        if sc and sc[0][0] > 0:
            best[q] = {"index": sc[0][1].index, "score": round(sc[0][0], 2)}
    return {"passages": [{"index": i, "heading": p["heading"], "text": p["text"],
                          "words": len(p["text"].split())} for i, p in enumerate(ps)],
            "best": best, "words": len(markdown.split())}


def bm25_table(versions, competitors, questions, top_k=5, passage_words=200):
    """For each question and each version of the Danfoss page (name -> markdown):
    page-level BM25 rank (the lab's default) and passage-level rank and best score,
    each against the same competitor pages, one Danfoss version at a time."""
    rows = []
    for q in questions:
        row = {"question": q, "versions": {}}
        for name, md in versions.items():
            page = _Page(name, "Danfoss", md)
            corpus = competitors + [page]
            ranked = lab.BM25(corpus).rank(q)
            prank = next(i for i, (_, d) in enumerate(ranked) if d is page) + 1
            pscore = next(s for s, d in ranked if d is page)
            pr = lab.PassageRanker(corpus, passage_words)
            ranked2 = pr.rank(q)
            srank = next(i for i, (_, d) in enumerate(ranked2) if d is page) + 1
            sscore = next(s for s, d in ranked2 if d is page)
            bp = pr.best(page, q, 1)
            row["versions"][name] = {
                "page_rank": prank, "page_score": round(pscore, 2),
                "page_top": prank <= top_k,
                "passage_rank": srank, "passage_score": round(sscore, 2),
                "passage_top": srank <= top_k,
                "best_heading": bp[0][1].heading if bp else ""}
        rows.append(row)
    return {"rows": rows, "pages": len(competitors) + 1, "top_k": top_k}


def lab_text(rebuilt_html):
    """The rebuilt page as the lab sees pages: the same extractor fetch_sources.py
    used for Danfoss's current page, so the comparison is fair."""
    return fetch_sources.html_to_text(rebuilt_html)


def lab_file(text, url, style="restructured"):
    return f"---\nbrand: Danfoss\nstyle: {style}\nurl: {url}\n---\n{text}\n"



# --- Markdown: the editable copy -----------------------------------------------------
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
CARD_RE = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?$")  # "[title](url): description"
FRONT_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def strip_links(s):
    return MD_LINK_RE.sub(r"\1", s or "")


def items_to_md(items, base=""):
    """Page items as editable Markdown: # headings, paragraphs, - lists, | tables |,
    [links](url)."""
    out = []
    for it in items:
        k = it["kind"]
        if k in ("h1", "h2", "h3"):
            out += ["", "#" * int(k[1]) + " " + it["text"], ""]
        elif k == "p":
            t = it["text"]
            if it.get("href"):
                t = f"[{t}]({urllib.parse.urljoin(base, it['href'])})"
            out += [t, ""]
        elif k == "ul":
            out += [f"- {x}" for x in it["items"]] + [""]
        elif k == "cards":  # catalog tiles: "- [title](url): description"
            out += [f"- [{c['title']}]({urllib.parse.urljoin(base, c['href'])}): {c['text']}"
                    for c in it["items"]] + [""]
        elif k == "table" and it["rows"]:
            rows = it["rows"]
            out += ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
            out += ["| " + " | ".join(r) + " |" for r in rows[1:]] + [""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def md_to_items(md):
    """Markdown back into page items. A line that is only a [link](url) becomes a
    link paragraph; links inside text are kept and rendered as links."""
    items, para, lst, tbl = [], [], [], []

    def flush():
        if para:
            text = " ".join(para)
            m = MD_LINK_RE.fullmatch(text.strip())
            items.append({"kind": "p", "text": m.group(1), "href": m.group(2)} if m
                         else {"kind": "p", "text": text})
            para.clear()
        if lst:
            cards = [CARD_RE.match(x) for x in lst]
            if all(cards) and any(m.group(3) for m in cards):
                items.append({"kind": "cards", "items": [
                    {"title": m.group(1), "href": m.group(2), "text": (m.group(3) or "").strip()}
                    for m in cards]})
            else:
                items.append({"kind": "ul", "items": lst[:]})
            lst.clear()
        if tbl:
            rows = [r for r in tbl if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
            if rows:
                items.append({"kind": "table", "rows": rows})
            tbl.clear()

    for line in md.splitlines():
        s = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            items.append({"kind": f"h{min(len(m.group(1)), 3)}",
                          "text": re.sub(r"[*_`]", "", m.group(2)).strip()})
        elif s.startswith("|"):
            if para or lst:
                flush()
            tbl.append([re.sub(r"\*\*|__|`", "", c).strip() for c in s.strip("|").split("|")])
        elif re.match(r"^([-*+]|\d+\.)\s+", s):
            if para or tbl:
                flush()
            lst.append(re.sub(r"\*\*|__|`", "", re.sub(r"^([-*+]|\d+\.)\s+", "", s)).strip())
        elif not s:
            flush()
        else:
            if lst or tbl:
                flush()
            para.append(re.sub(r"\*\*|__|`", "", s))
    flush()
    for i in [i for i, x in enumerate(items) if x["kind"] == "h1"][1:]:  # only one H1
        items[i]["kind"] = "h2"
    return items


def read_copy_text(text):
    """(frontmatter dict, Markdown body) of a copy's text."""
    m = FRONT_RE.match(text)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line[:1].isspace() and not line.startswith("-"):  # top-level keys only
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("'\"")
        text = text[m.end():]
    return meta, text


def read_copy(path):
    return read_copy_text(pathlib.Path(path).read_text(encoding="utf-8"))


def write_copy(path, meta, body):
    head = "\n".join(f'{k}: "{str(v).replace(chr(34), chr(39))}"' for k, v in meta.items())
    pathlib.Path(path).write_text(f"---\n{head}\n---\n{body.strip()}\n", encoding="utf-8")


def blocks_to_md(blocks, base=""):
    """The original page as Markdown, as it is: real heading levels (H4 stays H4),
    bold text that only looks like a heading stays **bold text**."""
    out = []
    for b in blocks:
        k, t = b["kind"], b["text"]
        if b.get("href"):
            t = f"[{t}]({urllib.parse.urljoin(base, b['href'])})"
        if k == "heading":
            out += ["", "#" * min(b["level"], 6) + " " + t, ""]
        elif b.get("pseudo"):
            out += [f"**{t}**", ""]
        elif k == "li":
            out.append("- " + t)
        elif k == "row":
            out.append("| " + " | ".join(b["cells"]) + " |")
        else:
            out += [t, ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def md_words(md):
    """Words of a Markdown text without its syntax (#, -, |, **, link targets)."""
    text = strip_links(md)
    text = re.sub(r"^\s*(#{1,6}|[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*$", " ", text, flags=re.M)
    text = text.replace("|", " ").replace("**", "").replace("__", "")
    return text.split()


def md_for_crawler(md):
    """Markdown with headings kept (for passages) but links and bold marks removed."""
    return strip_links(md).replace("**", "")


# --- robots.txt and sitemaps -------------------------------------------------------------
def robots_info(page_url):
    """robots.txt of the page's site: readable?, sitemaps declared, Googlebot allowed?"""
    import urllib.robotparser
    parts = urllib.parse.urlsplit(page_url)
    url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        why = fetch_sources.block_reason(e.read().decode("utf-8", errors="replace"), e.code)
        return {"url": url, "status": "blocked" if why else "error",
                "note": why or f"HTTP {e.code}", "sitemaps": [], "googlebot_allowed": None}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"url": url, "status": "error", "note": str(getattr(e, "reason", e)),
                "sitemaps": [], "googlebot_allowed": None}
    if "user-agent" not in text.lower():
        why = fetch_sources.block_reason(text) or "page that is not a robots.txt"
        return {"url": url, "status": "blocked", "note": why, "sitemaps": [], "googlebot_allowed": None}
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return {"url": url, "status": "ok", "note": "",
            "sitemaps": re.findall(r"(?im)^\s*sitemap:\s*(\S+)", text),
            "googlebot_allowed": rp.can_fetch("Googlebot", page_url)}


def robots_audit(r):
    if r["status"] != "ok":
        note = (f"Our download got a {r['note']} instead of robots.txt. Googlebot is usually let "
                "through such checks, but other crawlers (AI search bots) may get the same answer: "
                "worth asking the web team." if r["status"] == "blocked" else r["note"])
        return [{"check": "robots.txt", "value": r["status"],
                 "status": "bad" if r["status"] == "blocked" else "warn", "note": note}]
    n = len(r["sitemaps"])
    return [
        {"check": "robots.txt", "value": "readable", "status": "ok", "note": r["url"]},
        {"check": "Sitemap declared in robots.txt", "value": n, "status": "ok" if n else "warn",
         "note": ", ".join(r["sitemaps"][:3])},
        {"check": "Googlebot allowed by robots.txt", "value": "yes" if r["googlebot_allowed"] else "NO",
         "status": "ok" if r["googlebot_allowed"] else "bad"},
    ]


def write_sitemap(p):
    """sitemap.xml for the pages Atlas made for this product: the mini website's
    pages (webpage/site/), the product pages and any single reformatted page, each
    with its canonical URL and the date its copy last changed. Product page URLs
    are proposals until the pages are published."""
    paths = store_paths(p)
    site_dir = paths["folder"] / "site"
    entries = []
    for f in ([paths["rebuilt"]] + sorted(site_dir.glob("*.html"))
              + sorted((paths["folder"] / "products").glob("*.html"))):
        if not f.is_file():
            continue
        m = re.search(r'<link rel="canonical" href="([^"]+)"', f.read_text(encoding="utf-8"))
        loc = html.unescape(m.group(1)) if m else ""
        if loc.startswith("http") and loc not in [x for x, _ in entries]:  # template + AI: one URL
            src = f
            if f == paths["rebuilt"] and paths["copy"].is_file():
                src = paths["copy"]
            elif f.parent == site_dir and (site_dir / f.stem / "page.md").is_file():
                src = site_dir / f.stem / "page.md"
            entries.append((loc, datetime.date.fromtimestamp(src.stat().st_mtime).isoformat()))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           "<!-- Made by Atlas from the pages in this folder. Product page URLs are proposals. -->\n"
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "".join(f"  <url><loc>{html.escape(loc)}</loc><lastmod>{day}</lastmod></url>\n"
                     for loc, day in entries) + "</urlset>\n")
    paths["folder"].mkdir(parents=True, exist_ok=True)
    paths["sitemap"].write_text(xml, encoding="utf-8")
    return [loc for loc, _ in entries]


# --- the "Web page" tab ----------------------------------------------------------------
def store_paths(p):
    """A product's web page files (all committed except cache/):
      webpage/original.md     snapshot of Danfoss's page as it was copied (reference)
      webpage/original.json   what the copy found: download, metadata, crawler checks
      webpage/page.md         YOUR copy: edit it to adapt the page
      webpage/rebuilt.html    your copy as a crawler-friendly HTML page
      webpage/sitemap.xml     the pages made here, with dates
      webpage/products/       product pages (Model by model tab)
      webpage/cache/          the downloaded HTML (not committed)
      restructured_dir/restructured_1.md   rebuilt.html as the citation lab reads it"""
    folder = p["folder"] / "webpage"
    lab_dir = REPO / p["restructured_dir"] if p.get("restructured_dir") else folder
    return {"folder": folder, "cache": folder / "cache", "rebuilt": folder / "rebuilt.html",
            "copy": folder / "page.md", "original_md": folder / "original.md",
            "original_json": folder / "original.json", "sitemap": folder / "sitemap.xml",
            "lab": lab_dir / "restructured_1.md"}


def changes(original_md, removed, copy_md, allowed_numbers):
    """What the copy changed compared with Danfoss's page (words and numbers), and
    new numbers that are not in the wiki facts either."""
    import collections
    before = collections.Counter(_norm_words(md_words(original_md)))
    before -= collections.Counter(_norm_words([w for t in removed for w in t.split()]))
    after = collections.Counter(_norm_words(md_words(copy_md)))
    removed_w, added_w = before - after, after - before
    nb, na = set(numbers(md_words(original_md))), set(numbers(md_words(copy_md)))
    added_n = sorted(na - nb, key=lambda x: (len(x), x))
    return {"same": not removed_w and not added_w and nb == na,
            "words_before": sum(before.values()), "words_after": sum(after.values()),
            "removed": sorted(removed_w.elements())[:60], "added": sorted(added_w.elements())[:60],
            "numbers_removed": sorted(nb - na, key=lambda x: (len(x), x)),
            "numbers_added": added_n,
            "numbers_not_in_wiki": [n for n in added_n if n not in allowed_numbers],
            "removed_empty_sections": removed}
