#!/usr/bin/env python3
"""
Keep the ORIGINAL text of the Danfoss documents the wiki cites, in raw/.

The wiki is a compiled summary: compiling loses detail and caveats. The writer
gets the matching original passages next to the wiki facts, and the fact check
verifies claims against them (see generate_variants.py and app/verify.py).

  python Run.py update-raw              download every http(s) source cited in wiki/
  python lab/fetch_raw.py --force       download again, overwriting
  python lab/fetch_raw.py --wiki wiki --out raw

Each source becomes raw/<id>.md with a small header (url, fetched date). PDFs
need pypdf (in requirements.txt). A source the script cannot download, or one
without a URL in the wiki (for example the main eBrochure AD565353287087en-000101),
can be added by hand: put its text in raw/<id>.md with the same header, or drop
the PDF in raw/ and run this script again to convert it.
"""
import argparse
import datetime
import logging
import pathlib
import re
import sys

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise here
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import fetch_sources  # noqa: E402  (same downloader and PDF reader as the lab)

URL_RE = re.compile(r"https?://[^\s)\"'<>,]+")
SKIP = ("heatexchangers.danfoss.com",)  # a JavaScript hub with no text


def source_urls(wiki):
    urls = []
    for f in sorted(pathlib.Path(wiki).rglob("*.md")):
        for u in URL_RE.findall(f.read_text(encoding="utf-8")):
            u = u.rstrip(".,;")
            if u not in urls and not any(s in u for s in SKIP):
                urls.append(u)
    return urls


def raw_id(url):
    tail = [p for p in url.split("?")[0].split("/") if p][-1]
    tail = re.sub(r"\.pdf$", "", tail, flags=re.I)
    return re.sub(r"[^A-Za-z0-9-]+", "-", tail).strip("-").lower()[:80] or "source"


def header(url, kind):
    return (f"---\nurl: {url}\nkind: {kind}\nfetched: {datetime.date.today().isoformat()}\n"
            "note: Original text, not edited. The wiki summarises it.\n---\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki", default=str(REPO / "wiki"))
    ap.add_argument("--out", default=str(REPO / "raw"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(exist_ok=True)

    # PDFs dropped in raw/ by hand: convert them to text
    for pdf in sorted(out.glob("*.pdf")):
        target = out / f"{raw_id(pdf.name)}.md"
        if target.exists() and not args.force:
            continue
        text = fetch_sources.pdf_to_text(pdf.read_bytes())
        target.write_text(header(pdf.name, "pdf (added by hand)") + text + "\n", encoding="utf-8")
        print(f"  converted {pdf.name} -> {target.name} ({len(text.split())} words)")

    ok, failed = 0, []
    for url in source_urls(args.wiki):
        target = out / f"{raw_id(url)}.md"
        if target.exists() and not args.force:
            print(f"  kept   {target.name}")
            ok += 1
            continue
        print(f"  get    {url}", flush=True)
        try:
            text = fetch_sources.download(url)
        except Exception as e:  # noqa: BLE001  (403, bot checks, broken PDFs...)
            failed.append((url, str(e)))
            print(f"         FAILED: {e}")
            continue
        if len(text.split()) < 80:
            failed.append((url, f"only {len(text.split())} words"))
            print("         FAILED: almost no text")
            continue
        kind = "pdf" if url.lower().endswith(".pdf") else "web page"
        target.write_text(header(url, kind) + text + "\n", encoding="utf-8")
        print(f"         saved {target.name} ({len(text.split())} words)")
        ok += 1
    print(f"\n{ok} sources in {out}")
    if failed:
        print("Could not download (add their text by hand, see the top of this file):")
        for u, e in failed:
            print(f"  - {u}: {e}")


if __name__ == "__main__":
    main()
