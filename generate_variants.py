#!/usr/bin/env python3
"""
Role 3: generate the same page in 4 writing styles from one fact sheet,
using a local model through Ollama, then flag any number that is not in the
fact sheet (possible hallucination).

Only uses the Python standard library: no pip install needed.

Usage:
  python generate_variants.py --wiki wiki.md --topic "Example Pro invoicing software" \
      --model qwen3:8b --words 400 --runs 3

Output (folder ./variants):
  plain_1.md, stats_1.md, sources_1.md, stuffed_1.md, ...   (one file per page)
  report.json                                               (word counts + fact-check flags)
"""
import argparse
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
    with urllib.request.urlopen(req, timeout=1800) as resp:
        text = json.loads(resp.read())["response"]
    return THINK_RE.sub("", text).strip()  # drop reasoning blocks some models emit


def norm_numbers(text):
    """Set of numbers in text, with thousand/decimal separators removed so
    '1,200' and '1200' match."""
    return {re.sub(r"[.,]", "", n) for n in NUM_RE.findall(text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default="wiki.md")
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

    wiki = pathlib.Path(args.wiki).read_text(encoding="utf-8")
    keyword = args.keyword
    if not keyword:
        m = re.search(r"Target search phrase.*?\n-\s*(.+)", wiki)
        keyword = m.group(1).strip(" []") if m else args.topic

    allowed = norm_numbers(wiki)
    out = pathlib.Path(args.out)
    out.mkdir(exist_ok=True)
    report = []

    for style in args.styles.split(","):
        style = style.strip()
        if style not in STYLES:
            sys.exit(f"Unknown style: {style}")
        for run in range(1, args.runs + 1):
            prompt = PROMPT.format(
                topic=args.topic, words=args.words, wiki=wiki,
                style=STYLES[style].format(keyword=keyword),
            )
            name = f"{style}_{run}.md"
            path = out / name
            if path.exists() and path.stat().st_size > 0:
                print(f"Skipping {style} #{run} (already exists)", flush=True)
                page = path.read_text(encoding="utf-8").strip()
            else:
                print(f"Generating {style} #{run} ...", flush=True)
                page = call_ollama(args.host, args.model, prompt, args.temperature)
                path.write_text(page + "\n", encoding="utf-8")

            words = len(page.split())
            unknown = sorted(norm_numbers(page) - allowed, key=len)
            kw_count = page.lower().count(keyword.lower())
            entry = {
                "file": name, "style": style, "run": run, "words": words,
                "keyword_count": kw_count,
                "numbers_not_in_wiki": unknown,
                "length_ok": abs(words - args.words) <= 0.2 * args.words,
            }
            report.append(entry)

            flag = "  CHECK NUMBERS: " + ", ".join(unknown) if unknown else ""
            size = "" if entry["length_ok"] else f"  LENGTH OFF ({words} words)"
            print(f"  -> {name}: {words} words, keyword x{kw_count}{flag}{size}")

    (out / "report.json").write_text(json.dumps(
        {"model": args.model, "topic": args.topic, "keyword": keyword,
         "target_words": args.words, "pages": report}, indent=2),
        encoding="utf-8")
    print(f"\nDone. Pages and report.json are in {out}/")
    print("Now read every page by hand before handing it to the lab.")


if __name__ == "__main__":
    main()
