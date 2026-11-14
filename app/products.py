"""
Products and questions.

A product is a folder products/<slug>/ with:
  product.json     name, product type, application, search phrase, where its fact sheet is
  questions.json   which standard questions are switched off, and its own (case-specific) questions
  wiki/            the fact sheet as an OKF bundle (or "wiki" in product.json points elsewhere)
  sources.txt      optional fixed pages to compare against:  Brand | URL
  fixed/           those pages, downloaded
  sources/         pages found by source discovery
  runs/<date>/     every run: variants, lab results, the final page and report
  webpage/         Web page tab: the reformatted current page, product pages, cache/

Standard questions (questions/standard.json) are shared by every product. They can
use {product}, {a_product} (with a/an) and {application}, filled from product.json.
"""
import io
import json
import pathlib
import re
import sys
import uuid
import zipfile

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
PRODUCTS = REPO / "products"
STANDARD = REPO / "questions" / "standard.json"
sys.path.insert(0, str(REPO))
import generate_variants  # noqa: E402  (fact sheet loader and writing styles)

import ai  # noqa: E402


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "product"


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- products ------------------------------------------------------------------
def list_products():
    out = []
    if PRODUCTS.is_dir():
        for d in sorted(PRODUCTS.iterdir()):
            if (d / "product.json").is_file():
                p = get(d.name)
                out.append({"slug": p["slug"], "name": p["name"]})
    return out


def get(slug):
    folder = PRODUCTS / slug
    if not re.fullmatch(r"[a-z0-9-]+", slug or "") or not (folder / "product.json").is_file():
        raise ValueError(f"No product '{slug}'")
    p = _read(folder / "product.json", {})
    p["slug"] = slug
    p["folder"] = folder
    return p


def wiki_dir(p):
    return REPO / p["wiki"] if p.get("wiki") else p["folder"] / "wiki"


def fact_sheet(p):
    """The fact sheet as one Markdown text, or raises ValueError with what is wrong.
    Like the team's load_wiki: a folder is an OKF bundle, a single .md file is a
    ready-made fact sheet (e.g. a fact sheet .md file)."""
    path = wiki_dir(p)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    try:
        return generate_variants.load_okf_bundle(path)
    except SystemExit as e:  # the loader exits with a message on a broken bundle
        raise ValueError(str(e))


def guidelines(p):
    """The bundle's writing guidelines (wiki/guidelines/) for the writer prompt, or ''."""
    path = wiki_dir(p)
    if not path.is_dir():
        return ""
    try:
        return generate_variants.load_guidelines(path)
    except SystemExit as e:
        raise ValueError(str(e))


def keyword(p, sheet):
    if p.get("keyword"):
        return p["keyword"]
    m = re.search(r"Target search phrase.*?^\s*[-*]\s+(.+?)\s*$", sheet, re.DOTALL | re.MULTILINE)
    return m.group(1).strip(" []") if m else p.get("product_type") or p["name"]


def page_dirs(p):
    """Folders with comparison pages: fixed list, discovered sources, and extras."""
    dirs = [p["folder"] / "fixed", p["folder"] / "sources"]
    dirs += [REPO / d for d in p.get("extra_page_dirs", [])]
    # the reformatted current page from the Web page tab, where the lab reads it
    dirs.append(REPO / p["restructured_dir"] if p.get("restructured_dir") else p["folder"] / "webpage")
    return [d for d in dirs if d.is_dir()]


def source_list(p):
    path = REPO / p["source_list"] if p.get("source_list") else p["folder"] / "sources.txt"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "|" in line:
            brand, url = [x.strip() for x in line.split("|", 1)]
            rows.append((brand, url))
    return rows


# --- questions -----------------------------------------------------------------
def a_an(word):
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def fill(text, p):
    product = p.get("product_type") or p["name"]
    return (text.replace("{a_product}", a_an(product))
                .replace("{product}", product)
                .replace("{application}", p.get("application") or "my system"))


def standard_questions():
    return _read(STANDARD, [])


def add_standard(text):
    text = text.strip()
    if not text:
        raise ValueError("Type a question first")
    qs = standard_questions()
    qs.append({"id": "s-" + uuid.uuid4().hex[:8], "text": text})
    _write(STANDARD, qs)


def delete_standard(qid):
    _write(STANDARD, [q for q in standard_questions() if q["id"] != qid])


def _qfile(p):
    return p["folder"] / "questions.json"


def questions(p):
    """Every question for this product: standard ones (filled in) then its own."""
    sel = _read(_qfile(p), {"disabled_standard": [], "custom": []})
    off = set(sel.get("disabled_standard", []))
    out = [{"id": q["id"], "kind": "standard", "template": q["text"],
            "text": fill(q["text"], p), "enabled": q["id"] not in off}
           for q in standard_questions()]
    out += [{"id": q["id"], "kind": "custom", "template": q["text"], "text": q["text"],
             "enabled": q.get("enabled", True)} for q in sel.get("custom", [])]
    return out


def set_enabled(p, enabled_ids):
    enabled_ids = set(enabled_ids)
    sel = _read(_qfile(p), {"disabled_standard": [], "custom": []})
    sel["disabled_standard"] = [q["id"] for q in standard_questions() if q["id"] not in enabled_ids]
    for q in sel.get("custom", []):
        q["enabled"] = q["id"] in enabled_ids
    _write(_qfile(p), sel)


def add_custom(p, text):
    text = text.strip()
    if not text:
        raise ValueError("Type a question first")
    sel = _read(_qfile(p), {"disabled_standard": [], "custom": []})
    sel.setdefault("custom", []).append({"id": "c-" + uuid.uuid4().hex[:8], "text": text, "enabled": True})
    _write(_qfile(p), sel)


def delete_custom(p, qid):
    sel = _read(_qfile(p), {"disabled_standard": [], "custom": []})
    sel["custom"] = [q for q in sel.get("custom", []) if q["id"] != qid]
    _write(_qfile(p), sel)


# --- adding a product from a brochure --------------------------------------------
def extract_text(filename, data):
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            import pypdf
        except ImportError:
            raise ValueError("Reading PDFs needs pypdf. Run:  pip install pypdf")
        reader = pypdf.PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        import html
        text = html.unescape(text)
    elif name.endswith((".txt", ".md", ".markdown", ".csv")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError("Upload a PDF, Word (.docx), text or Markdown file")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text.split()) < 30:
        raise ValueError("Almost no text found in this file. If it is a scanned PDF, "
                         "copy the text into a .txt file and upload that instead.")
    return text


DRAFT_PROMPT = """You turn a product brochure into a fact sheet for a web page writer.
Return ONLY a JSON object with these keys:
  "name":         full product name, e.g. "Danfoss Micro Plate brazed plate heat exchangers for heat pumps"
  "product_type": the generic kind of product, lower case, singular, no brand, e.g. "brazed plate heat exchanger"
  "application":  its main use, lower case, e.g. "heat pumps"
  "keyword":      the search phrase a buyer would type to find this kind of product
  "facts":        the fact sheet in Markdown, with these sections:
                  # What it is / # Who it is for / # Main problem it solves / # Key features /
                  # Typical uses / # Models and sizes / # Figures / # Quotes / # Price
  "never_claim":  Markdown bullet list of claims the brochure does NOT support and pages must never make
RULES for "facts": copy facts, figures, model names, quotes (with who said them) and units EXACTLY
as in the brochure. Do not add anything that is not in the brochure. If a section has nothing,
write "Not stated in the brochure."

BROCHURE:
{text}
"""


DRAFT_KEYS = ("name", "product_type", "application", "keyword", "facts", "never_claim")


def brochure_limit(provider):
    """How much brochure text goes to the AI: a local model reads less at once than Gemini."""
    return 30000 if ai.providers().get(provider, {}).get("type") == "ollama" else 60000


def _as_markdown(v, level=1):
    """Small models sometimes return the fact sheet as nested JSON instead of one
    Markdown string. Turn it back into Markdown instead of failing."""
    if isinstance(v, dict):
        return "\n\n".join(f"{'#' * level} {k}\n{_as_markdown(x, level + 1)}" for k, x in v.items())
    if isinstance(v, list):
        return "\n".join(f"- {_as_markdown(x, level + 1)}" for x in v)
    return str(v or "").strip()


def clean_draft(d):
    if not isinstance(d, dict):
        raise ValueError("The AI's answer had the wrong shape")
    d = {k.lower().strip(): v for k, v in d.items()}
    out = {k: _as_markdown(d.get(k, "")) for k in DRAFT_KEYS}
    if not out["facts"]:
        raise ValueError("The AI did not write any facts")
    return out


def draft_from_brochure(text, provider, model):
    answer = ai.chat(provider, model, "", DRAFT_PROMPT.format(text=text[:brochure_limit(provider)]),
                     temperature=0.1, use_cache=False)
    return clean_draft(ai.parse_json(answer))


def create_product(d):
    name = d.get("name", "").strip()
    if not name or not d.get("facts", "").strip():
        raise ValueError("A product needs at least a name and facts")
    slug = slugify(d.get("slug") or name)
    base, n = slug, 2
    while (PRODUCTS / slug).exists():
        slug, n = f"{base}-{n}", n + 1
    folder = PRODUCTS / slug
    wiki = folder / "wiki"
    wiki.mkdir(parents=True)

    def yaml(s):
        return "'" + s.replace("'", "''") + "'"

    facts = d["facts"].strip()
    (wiki / "product.md").write_text(
        f"---\ntype: Product\ntitle: {yaml(name)}\n"
        f"description: {yaml(d.get('product_type', '') + ' for ' + d.get('application', ''))}\n---\n"
        f"{facts}\n", encoding="utf-8")
    never = d.get("never_claim", "").strip() or (
        "- \"the best\", \"number 1\" or \"outperforms all other products\" unless the facts prove it\n"
        "- any figure, certification, award, customer or price that is not in the facts")
    (wiki / "never-claim.md").write_text(
        "---\ntype: Policy\ntitle: Never claim\n"
        "description: Claims that generated pages must never make.\n---\n"
        f"# Never claim\n{never}\n", encoding="utf-8")
    # OKF index: the generator reads concepts in this order, facts first
    (wiki / "index.md").write_text(
        "# Concepts\n* [Product](product.md) - the facts.\n"
        "* [Never claim](never-claim.md) - claims pages must not make.\n", encoding="utf-8")

    urls = []
    for line in d.get("danfoss_urls", "").splitlines():
        if line.strip().startswith("http"):
            urls.append(f"Danfoss | {line.strip()}")
    for line in d.get("competitor_urls", "").splitlines():
        line = line.strip()
        if "|" in line:
            urls.append(line)
        elif line.startswith("http"):
            host = re.sub(r"^www\.", "", line.split("/")[2])
            urls.append(f"{host.split('.')[0].capitalize()} | {line}")
    if urls:
        (folder / "sources.txt").write_text(
            "# Fixed pages to compare against.  Brand | URL\n" + "\n".join(urls) + "\n",
            encoding="utf-8")

    _write(folder / "product.json", {
        "name": name, "product_type": d.get("product_type", "").strip(),
        "application": d.get("application", "").strip(),
        "keyword": d.get("keyword", "").strip()})
    _write(folder / "questions.json", {"disabled_standard": [], "custom": []})
    return slug
