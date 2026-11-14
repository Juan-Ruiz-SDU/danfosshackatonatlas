#!/usr/bin/env python3
"""
Download the public pages listed in sources.txt and save them as clean text,
ready for experiment.py.

  python lab/fetch_sources.py              download everything in lab/sources.txt
  python lab/fetch_sources.py --force      download again, overwriting saved pages

Output:
  lab/corpus/competitors/<brand>_<n>.md        competitor pages
  lab/corpus/danfoss_original/original_<n>.md  Danfoss's own public pages (baseline)

Each file starts with a small header (brand, url, style) and is plain text.
If a site blocks the download, open the page in your browser, copy the text and
save it by hand in the same folder with the same header: the lab reads any .md
or .txt file there.

Standard library only. PDFs need:  pip install pypdf
"""
import argparse
import html.parser
import io
import pathlib
import re
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "svg",
             "form", "button", "iframe", "aside"}
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
              "br", "section", "article", "td", "th", "dd", "dt"}


class TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
            if tag in {"h1", "h2", "h3"}:
                self.parts.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw):
    p = TextExtractor()
    p.feed(raw)
    return tidy("".join(p.parts))


def pdf_to_text(data):
    try:
        import pypdf
    except ImportError:
        sys.exit("This source is a PDF. Install the PDF reader first:  pip install pypdf")
    reader = pypdf.PdfReader(io.BytesIO(data))
    return tidy("\n".join(page.extract_text() or "" for page in reader.pages))


def tidy(text):
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in text.splitlines()]
    # drop menu crumbs: very short lines that are not headings
    lines = [l for l in lines if len(l) > 25 or l.startswith("#")]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# Bot protection pages: the site answers with a check (JavaScript challenge,
# captcha, "access denied") instead of the page. Strong markers are enough on
# their own; weak ones only count on a page with almost no text.
BLOCK_STRONG = [
    (r"Azure WAF|/\.azwaf/", "Azure WAF bot check"),
    (r"cf-chl-|challenges\.cloudflare\.com|cf_chl_opt", "Cloudflare bot check"),
    (r"_Incapsula_Resource|Incapsula incident", "Imperva/Incapsula bot check"),
    (r"akamai.{0,40}(?:bot manager|access denied)|Reference #\d+\.\w+\.\d+", "Akamai bot check"),
]
BLOCK_WEAK = [
    (r"Please enable JavaScript|enable cookies|Just a moment\.\.\.", "page that needs JavaScript or cookies"),
    (r"captcha|are you a robot|verify you are human", "captcha"),
    (r"Access Denied|Forbidden|Request blocked|unusual traffic", "access denied"),
]


class Blocked(Exception):
    """The site answered with a bot check instead of the page."""


def block_reason(raw_html, status=200):
    """Why this response is a bot check and not the page, or None."""
    for pat, why in BLOCK_STRONG:
        if re.search(pat, raw_html, re.I):
            return why
    words = len(html_to_text(raw_html).split()) if raw_html else 0
    if status in (401, 403, 429, 503) or words < 150:
        for pat, why in BLOCK_WEAK:
            if re.search(pat, raw_html, re.I):
                return why
        if status in (401, 403, 429, 503):
            return f"HTTP {status}"
    return None


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en,fr;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        why = block_reason(e.read().decode("utf-8", errors="replace"), e.code)
        if why:
            raise Blocked(f"the site answered with a {why} instead of the page "
                          "(copy the text by hand, see the top of this file)")
        raise
    if "pdf" in ctype or url.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return pdf_to_text(data)
    charset = re.search(r"charset=([\w-]+)", ctype)
    raw = data.decode(charset.group(1) if charset else "utf-8", errors="replace")
    why = block_reason(raw)
    if why:
        raise Blocked(f"the site answered with a {why} instead of the page "
                      "(copy the text by hand, see the top of this file)")
    return html_to_text(raw)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(HERE / "sources.txt"))
    ap.add_argument("--out", default=str(HERE / "corpus"))
    ap.add_argument("--force", action="store_true", help="overwrite saved pages")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    counters, ok, failed = {}, 0, []
    for line in pathlib.Path(args.sources).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        brand, url = [x.strip() for x in line.split("|", 1)]
        n = counters[brand] = counters.get(brand, 0) + 1
        if brand.lower() == "danfoss":
            folder, name, style = out / "danfoss_original", f"original_{n}.md", "original"
        else:
            folder, name, style = out / "competitors", f"{slug(brand)}_{n}.md", "competitor"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        if path.exists() and not args.force:
            print(f"  kept   {path.relative_to(out)} (already saved)")
            ok += 1
            continue
        print(f"  get    {brand}: {url}", flush=True)
        try:
            text = download(url)
        except Exception as e:  # network errors, 403s, broken PDFs...
            failed.append((brand, url, str(e)))
            print(f"         FAILED: {e}")
            continue
        words = len(text.split())
        if words < 80:
            failed.append((brand, url, f"only {words} words (page probably needs JavaScript)"))
            print(f"         FAILED: only {words} words of text")
            continue
        path.write_text(f"---\nbrand: {brand}\nstyle: {style}\nurl: {url}\n---\n{text}\n",
                        encoding="utf-8")
        print(f"         saved {path.relative_to(out)} ({words} words)")
        ok += 1

    print(f"\n{ok} pages ready in {out}")
    if failed:
        print(f"{len(failed)} failed. Copy these by hand (see the note at the top of this file):")
        for brand, url, err in failed:
            print(f"  - {brand}: {url}\n    {err}")


if __name__ == "__main__":
    main()
