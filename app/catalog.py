"""
The "Model by model" tab: the list of products inside a product family, and
one web page per product, built only from the fact sheet.

The list comes from the fact sheet itself: the first Markdown table with a
"Models" column (for Micro Plate: the heat pump platforms table). Each row is one
product. Other tables that share the first column (e.g. the pressure table's
"Platform" column) add their rows to the matching product.

Two versions of each product page:
  template   every sentence copied from the fact sheet, laid out by the page
             structure guideline: nothing can be invented
  ai         the writer AI rewrites the template's facts into a page; numbers not
             in the product's facts and never-claim words are flagged
"""
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO))
import generate_variants as gv  # noqa: E402

import ai  # noqa: E402
import products  # noqa: E402
import webpage  # noqa: E402

SECTION_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
FOOT_RE = re.compile(r"\[\^[^\]]+\]")
SERVICE_TYPES = {"service", "software tool"}
SKIP_TYPES = {"policy", "reference", "test parameter", "guideline", "website", "company"}


def _clean(s):
    s = LINK_RE.sub(r"\1", FOOT_RE.sub("", s))
    return re.sub(r"\s+", " ", s).strip()


def concepts(p):
    """[(fm, body)] of the product's OKF bundle, or [] for a single-file fact sheet."""
    path = products.wiki_dir(p)
    if not path.is_dir():
        return []
    try:
        return [(fm, body) for fm, body, _ in gv._concepts(path)]
    except SystemExit as e:
        raise ValueError(str(e))


def sections(body):
    """{heading: [lines]} of a concept body (footnote definitions dropped)."""
    out, cur = {}, "_"
    for line in body.splitlines():
        if re.match(r"^\[\^[^\]]+\]:", line):
            continue
        m = SECTION_RE.match(line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, [])
        elif line.strip():
            out.setdefault(cur, []).append(line.rstrip())
    return out


def bullets(lines):
    return [_clean(l.lstrip("-* ").strip()) for l in lines
            if l.strip().startswith(("-", "*")) and _clean(l.lstrip("-* "))]


def tables(text):
    """[(heading above it, header, rows)] of every Markdown table in a text."""
    out, cur, heading = [], [], ""
    for line in text.splitlines() + [""]:
        m = SECTION_RE.match(line.strip())
        if m and not cur:
            heading = _clean(m.group(1))
        if line.strip().startswith("|"):
            cur.append([_clean(c) for c in line.strip().strip("|").split("|")])
        elif cur:
            rows = [r for r in cur if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
            if len(rows) >= 2:
                out.append((heading, rows[0], rows[1:]))
            cur = []
    return out


def catalog(p):
    """{'key': column name, 'columns': [...], 'items': [{id, cells, label, extra}]}."""
    all_tables = []
    for fm, body in concepts(p):
        all_tables += [(fm, title, h, rows) for title, h, rows in tables(body)]
    main = next(((fm, h, rows) for fm, _, h, rows in all_tables
                 if any("model" in c.lower() for c in h)), None)
    if not main:
        return {"key": "", "columns": [], "items": [], "note":
                "The fact sheet has no table with a 'Models' column, so there is no product list."}
    fm, head, rows = main
    key = head[0]
    items = []
    for r in rows:
        r = (r + [""] * len(head))[:len(head)]
        extra = []
        for fm2, title2, h2, rows2 in all_tables:
            if h2 is head or key not in h2:
                continue
            k = h2.index(key)
            match = [x for x in rows2 if len(x) > k and x[k] == r[0]]
            if match:
                extra.append({"title": title2, "columns": h2, "rows": match})
        label = " · ".join(f"{h}: {c}" for h, c in zip(head[1:], r[1:]) if c)
        items.append({"id": r[0], "cells": r, "label": label, "extra": extra})
    return {"key": key, "columns": head, "items": items, "source": fm.get("title", "")}


def _item(p, item_id):
    cat = catalog(p)
    it = next((x for x in cat["items"] if x["id"] == item_id), None)
    if not it:
        raise ValueError(f"No product '{item_id}' in the list")
    return cat, it


def facts_for(p, item_id):
    """The facts one product page may use, as Markdown items for render_html and
    as Markdown text for the AI. Every sentence comes from the fact sheet."""
    cat, it = _item(p, item_id)
    cs = concepts(p)
    product = next(((fm, b) for fm, b in cs if fm.get("type", "").lower() == "product"), None)
    family = (product[0].get("title") if product else None) or p["name"]
    row_text = " ".join(it["cells"]).lower()
    items = [{"kind": "h1", "text": f"{family}: {cat['key']} {it['id']}"}]
    if product:
        if product[0].get("description"):
            items.append({"kind": "p", "text": _clean(product[0]["description"])})
        what = sections(product[1]).get("What it is", [])
        if what:
            items.append({"kind": "p", "text": _clean(" ".join(what))})

    # specifications: the row, then rows of related tables
    items.append({"kind": "h2", "text": f"{cat['key']} {it['id']} specifications"})
    items.append({"kind": "table", "rows": [["Specification", "Value"]]
                  + [[h, c] for h, c in zip(cat["columns"][1:], it["cells"][1:]) if c]})
    for ex in it["extra"]:
        cols = [c for c in ex["columns"] if c != cat["key"]]
        k = ex["columns"].index(cat["key"])
        rows = [[c for j, c in enumerate(r) if j != k] for r in ex["rows"]]
        items.append({"kind": "h3", "text": ex.get("title") or " / ".join(cols[1:]) or "More data"})
        items.append({"kind": "table", "rows": [cols] + rows})

    # facts from the concept that holds the table (e.g. refrigerants) ...
    for fm, body in cs:
        if _clean(fm.get("title", "")) == cat.get("source"):
            facts = [b for b in bullets(sections(body).get("Summary", [])) if "refrigerant" in b.lower()]
            if facts:
                items.append({"kind": "h2", "text": "Refrigerants"})
                items.append({"kind": "ul", "items": facts})
    # ... and concepts the row names (e.g. "double wall" -> Double wall option),
    # section by section so each list keeps its heading
    for fm, body in cs:
        t = fm.get("type", "").lower()
        title = _clean(fm.get("title", ""))
        if t in SKIP_TYPES or t == "product" or title == cat.get("source"):
            continue
        name = " ".join(re.sub(r"[™®]", "", title).lower().split()[:2])
        if not name or name not in row_text:
            continue
        items.append({"kind": "h2", "text": title})
        for head, lines in sections(body).items():
            facts = bullets(lines)
            if not facts:
                continue
            if head not in ("_", "Facts"):
                items.append({"kind": "h3", "text": _clean(head)})
            items.append({"kind": "ul", "items": facts})

    if product:
        ps = sections(product[1])
        feats = bullets(ps.get("Key features", []))
        if feats:
            items.append({"kind": "h2", "text": f"Key features of {family}"})
            items.append({"kind": "ul", "items": feats})
        uses = ps.get("Typical uses", [])
        if uses:
            items.append({"kind": "h2", "text": "Typical uses"})
            items.append({"kind": "p", "text": _clean(" ".join(uses))})
    svc = [(fm, b) for fm, b in cs if fm.get("type", "").lower() in SERVICE_TYPES]
    if svc:
        items.append({"kind": "h2", "text": "Selection and testing"})
        for fm, body in svc:
            facts = [b for lines in sections(body).values() for b in bullets(lines)]
            if facts:
                items.append({"kind": "h3", "text": _clean(fm.get("title", ""))})
                items.append({"kind": "ul", "items": facts})
    return items


def proposed_url(p, slug_id):
    """A proposed address for a product page: under the product's own page in the
    mini website (Web page tab), or a local anchor if there is none yet."""
    import website  # here, not at the top: website imports webpage too
    danfoss = next((u for b, u in products.source_list(p) if b.lower() == "danfoss"), "")
    pid = website.lab_page(p, danfoss)
    copy = website.page_paths(p, pid)["copy"] if pid else None
    base = webpage.read_copy(copy)[0].get("url", "") if copy and copy.is_file() else ""
    if not base.startswith("http"):
        return f"#{slug_id}"
    return base.rstrip("/") + f"/{slug_id}/"


def product_meta(items, p):
    h1 = items[0]["text"]
    desc = next((x["text"] for x in items if x["kind"] == "p"), "")
    if len(desc) > 160:
        desc = desc[:157].rsplit(" ", 1)[0] + "..."
    return {"title": h1, "description": desc}


REWRITE_STYLE = (
    "A product page for one product of the range. Use every figure from the fact sheet "
    "precisely, keep the specifications in a Markdown table, give each topic its own ## "
    "heading in the buyer's words, and start each section with the direct answer. "
    "Do NOT mention where the figures come from and do NOT include quotes."
)


def build(p, item_id, questions, competitors, version="template", provider=None, model=None,
          fresh=False):
    """One product page (template or AI rewrite), saved as HTML, with checks and
    the crawler / BM25 views."""
    items = facts_for(p, item_id)
    facts_md = webpage.to_markdown(items)
    flags = {"numbers_not_in_facts": [], "claims": []}
    if version == "ai":
        guide = gv.load_guidelines(products.wiki_dir(p)) if products.wiki_dir(p).is_dir() else ""
        never = next((b for fm, b in concepts(p) if fm.get("title", "").lower() == "never claim"), "")
        prompt = gv.build_prompt(items[0]["text"], 350,
                                 facts_md + ("\n\n## Never claim\n" + never if never else ""),
                                 REWRITE_STYLE, guide)
        text = ai.chat(provider, model, "", prompt, temperature=0.3, use_cache=not fresh)
        text = re.sub(r"\A```(?:markdown|md)?\s*\n(.*?)\n```\s*\Z", r"\1", text.strip(), flags=re.DOTALL)
        page_items = webpage.md_to_items(text)
        if not page_items or page_items[0]["kind"] != "h1":
            page_items.insert(0, {"kind": "h1", "text": items[0]["text"]})
        allowed = gv.norm_numbers(facts_md)
        flags["numbers_not_in_facts"] = sorted(gv.norm_numbers(text) - allowed, key=len)
        md = webpage.to_markdown(page_items)  # bold/italic marks removed
        flags["claims"] = webpage.claim_flags(md)
    else:
        page_items, md = items, facts_md
    meta = product_meta(page_items, p)
    cat = catalog(p)
    slug_id = re.sub(r"[^a-z0-9]+", "-", f"{cat['key']}-{item_id}".lower()).strip("-")
    html_text = webpage.render_html(page_items, meta, proposed_url(p, slug_id), None, "en",
                                    note="Built from the Atlas fact sheet only. "
                                         + ("Rewritten by AI: check the flags before use."
                                            if version == "ai" else "Every sentence comes from the fact sheet."))
    folder = webpage.store_paths(p)["folder"] / "products"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{slug_id}{'-ai' if version == 'ai' else ''}.html"
    (folder / name).write_text(html_text, encoding="utf-8")
    listed = webpage.write_sitemap(p)
    rmeta, _ = webpage.parse_page(html_text)
    checks = webpage.audit(rmeta, page_items, None, page_items)
    url = proposed_url(p, slug_id)
    checks.append({"check": "Listed in sitemap.xml", "value": "yes" if url in listed else "no",
                   "status": "ok" if url in listed else "warn",
                   "note": f"proposed URL {url}" if url.startswith("http")
                   else "make the copy in the Web page tab first, so product pages get a URL"})
    return {
        "id": item_id, "version": version, "file": f"products/{name}", "words": len(md.split()),
        "flags": flags, "audit": checks,
        "googlebot": webpage.googlebot_view(md, questions),
        "bm25": webpage.bm25_table({version: md}, competitors, questions),
    }
