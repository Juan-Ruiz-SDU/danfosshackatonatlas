#!/usr/bin/env python3
"""
Role 3: generate the same page in 4 writing styles from one fact sheet,
using a local model through Ollama, then flag any number that is not in the
fact sheet (possible hallucination).

The fact sheet is an Open Knowledge Format (OKF v0.2) bundle: a folder of
Markdown concept files with YAML frontmatter (see wiki/index.md).

Only uses the Python standard library: no pip install needed.

Usage:
  python generate_variants.py --wiki wiki --topic "Example Pro invoicing software" \
      --model qwen3:8b --words 400 --runs 3

Output (folder ./variants). Earlier pages are never overwritten, so the
progress between runs stays visible:
  plain_1.md, stats_1.md, sources_1.md, stuffed_1.md, ...   (one file per page;
                                      numbering continues after existing pages)
  report.json        (one entry per page: word count, fact-check flags, model,
                      wiki and date; new entries are appended after each page)
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
import urllib.request

STYLES = {
    "plain": (
        "Plain, neutral description. Explain what the product is, who it is for "
        "and what it does. Do NOT include statistics, numbers (except the price), "
        "quotes or references to sources."
    ),
    "stats": (
        "Fact-dense. Include every relevant figure from the fact sheet "
        "(numbers, percentages, ratings, prices) stated precisely. "
        "Do NOT mention where the figures come from and do NOT include quotes."
    ),
    "sources": (
        "Fact-dense and well sourced. Include every relevant figure from the fact "
        "sheet AND say where each one comes from (e.g. 'according to ...'). "
        "Include the quotes from the fact sheet with their attribution, and list "
        "the external sources at the end under 'Sources'."
    ),
    "stuffed": (
        "Keyword-stuffed TEST version (for a lab experiment only, never to be "
        "published). Use the exact phrase \"{keyword}\" as often as possible: in the "
        "title, every heading and most sentences. Otherwise plain description, "
        "no statistics, no sources."
    ),
}

PROMPT = """You are writing a public web page about: {topic}

RULES:
- Use ONLY facts from the FACT SHEET below.
- Do not add any number, name, date, source, quote or claim that is not in the fact sheet.
- If something is missing from the fact sheet, leave it out. Never guess.
- Respect the "Never claim" list.
- Write about {words} words, in English, in Markdown, starting with a # title.
- Output only the page, nothing else.

STYLE:
{style}

FACT SHEET:
{wiki}
"""

NUM_RE = re.compile(r"\d[\d.,]*\d|\d")
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# --- OKF bundle loading ------------------------------------------------------
OKF_RESERVED = {"index.md", "log.md"}  # OKF v0.2 section 3.1: not concepts
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
TOP_KEY_RE = re.compile(r"([A-Za-z_][\w-]*):[ \t]*(.*?)[ \t]*$")
# Links to other concepts in the bundle (not http/https): keep only the text,
# so bundle paths never leak into the generated pages.
INTERNAL_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!https?://)[^)]*\)")
# Footnotes cite the eBrochure in every concept; the source is already stated
# once in the "Single source of truth" policy, so drop them from the prompt.
FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]:.*\n?", re.MULTILINE)
FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]]+\]")
LINK_TARGET_RE = re.compile(r"\]\(([^)#\s]+)\)")


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        quote, value = value[0], value[1:-1]
        if quote == "'":
            value = value.replace("''", "'")  # YAML escape inside '...'
    return value


def parse_concept(text):
    """Return (frontmatter top-level scalars, body), or (None, text) if the
    file has no frontmatter. Nested YAML (sources, generated...) is skipped:
    it is provenance metadata, not facts for the page."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).splitlines():
        km = TOP_KEY_RE.match(line)  # unindented lines only = top-level keys
        if km:
            fm[km.group(1)] = unquote(km.group(2))
    return fm, text[m.end():]


def ordered_concepts(directory):
    """Concept files in the order each folder's index.md lists them (OKF
    progressive disclosure), then any unlisted files alphabetically."""
    order = []
    index = directory / "index.md"
    if index.is_file():
        for target in LINK_TARGET_RE.findall(index.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("/"):
                continue
            p = directory / target
            p = p.parent if p.name == "index.md" else p
            if p not in order:
                order.append(p)
    for p in order + sorted(p for p in directory.iterdir() if p not in order):
        if p.is_dir():
            yield from ordered_concepts(p)
        elif p.is_file() and p.suffix == ".md" and p.name not in OKF_RESERVED:
            yield p


def load_okf_bundle(root):
    """Check OKF v0.2 conformance (every concept has frontmatter with a
    non-empty `type`) and render all concepts as one fact sheet for the LLM."""
    root = pathlib.Path(root)
    if not root.is_dir():
        sys.exit(f"{root} is not an OKF bundle folder (expected e.g. --wiki wiki)")
    parts, problems = [], []
    for path in ordered_concepts(root):
        rel = path.relative_to(root).as_posix()
        fm, body = parse_concept(path.read_text(encoding="utf-8"))
        if fm is None:
            problems.append(f"{rel}: no YAML frontmatter")
            continue
        if not fm.get("type"):
            problems.append(f"{rel}: frontmatter has no `type`")
            continue
        title = fm.get("title") or path.stem.replace("-", " ")
        body = INTERNAL_LINK_RE.sub(r"\1", body)
        body = FOOTNOTE_REF_RE.sub("", FOOTNOTE_DEF_RE.sub("", body))
        body = re.sub(r"^(#{1,4}) ", r"##\1 ", body, flags=re.MULTILINE)
        head = f"## {title}\n" + (fm["description"] + "\n" if fm.get("description") else "")
        parts.append(head + "\n" + body.strip())
    if problems:
        sys.exit("Not a conformant OKF bundle:\n  " + "\n  ".join(problems))
    if not parts:
        sys.exit(f"No concept files found in {root}")
    return "# FACT SHEET (single source of truth)\n\n" + "\n\n".join(parts) + "\n"


# --- output: keep every earlier page and report entry ------------------------
def next_run(out, style):
    """First free run number for a style, so earlier pages are never overwritten."""
    done = [int(m.group(1)) for p in out.glob(f"{style}_*.md")
            if (m := re.fullmatch(rf"{re.escape(style)}_(\d+)\.md", p.name))]
    return max(done, default=0) + 1


def load_report(path):
    """Entries already in report.json. The old one-batch format (model, topic...
    at the top level) is flattened into each page entry."""
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    shared = {k: v for k, v in data.items() if k != "pages"}
    if shared:  # old format: written by the pre-OKF script, which read wiki.md
        shared.setdefault("wiki", "wiki.md")
    return [{**shared, **page} for page in data.get("pages", [])]


def call_ollama(host, model, prompt, temperature):
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        text = json.loads(resp.read())["response"]
    return THINK_RE.sub("", text).strip()  # drop reasoning blocks some models emit


def norm_numbers(text):
    """Set of numbers in text, with thousand/decimal separators removed so
    '1,200' and '1200' match."""
    return {re.sub(r"[.,]", "", n) for n in NUM_RE.findall(text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default="wiki", help="OKF bundle folder")
    ap.add_argument("--topic", required=True, help="what the page is about")
    ap.add_argument("--keyword", help="phrase for the stuffed variant "
                    "(default: taken from the wiki's 'Target search phrase')")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--words", type=int, default=400)
    ap.add_argument("--runs", type=int, default=1, help="pages per style")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--styles", default=",".join(STYLES), help="comma list")
    ap.add_argument("--out", default="variants")
    args = ap.parse_args()

    wiki = load_okf_bundle(args.wiki)
    keyword = args.keyword
    if not keyword:
        # first bullet after the "Target search phrase" heading
        m = re.search(r"Target search phrase.*?^\s*[-*]\s+(.+?)\s*$", wiki,
                      re.DOTALL | re.MULTILINE)
        keyword = m.group(1).strip(" []") if m else args.topic

    allowed = norm_numbers(wiki)
    out = pathlib.Path(args.out)
    out.mkdir(exist_ok=True)
    report_path = out / "report.json"
    report = load_report(report_path)

    for style in args.styles.split(","):
        style = style.strip()
        if style not in STYLES:
            sys.exit(f"Unknown style: {style}")
        first = next_run(out, style)
        for run in range(first, first + args.runs):
            prompt = PROMPT.format(
                topic=args.topic, words=args.words, wiki=wiki,
                style=STYLES[style].format(keyword=keyword),
            )
            print(f"Generating {style} #{run} ...", flush=True)
            page = call_ollama(args.host, args.model, prompt, args.temperature)

            name = f"{style}_{run}.md"
            (out / name).write_text(page + "\n", encoding="utf-8")

            words = len(page.split())
            unknown = sorted(norm_numbers(page) - allowed, key=len)
            kw_count = page.lower().count(keyword.lower())
            entry = {
                "file": name, "style": style, "run": run, "words": words,
                "keyword_count": kw_count,
                "numbers_not_in_wiki": unknown,
                "length_ok": abs(words - args.words) <= 0.2 * args.words,
                "model": args.model, "topic": args.topic, "keyword": keyword,
                "target_words": args.words, "wiki": args.wiki,
                "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            report.append(entry)
            # saved after every page, so an interrupted run keeps its entries
            report_path.write_text(json.dumps({"pages": report}, indent=2),
                                   encoding="utf-8")

            flag = "  CHECK NUMBERS: " + ", ".join(unknown) if unknown else ""
            size = "" if entry["length_ok"] else f"  LENGTH OFF ({words} words)"
            print(f"  -> {name}: {words} words, keyword x{kw_count}{flag}{size}")

    print(f"\nDone. New pages and report.json are in {out}/ (earlier pages kept)")
    print("Now read every page by hand before handing it to the lab.")


if __name__ == "__main__":
    main()
