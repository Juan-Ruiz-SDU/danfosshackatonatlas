#!/usr/bin/env python3
"""
Ask Gemini (with Google Search) every prompt in prompts/prompts.txt, record
which web pages it used for each answer, and import those pages as clean text.

It only runs when you start it, so nothing is regenerated behind your back.
Run it again whenever you want to refresh the sources:

  python Run.py update-sources                    same as below, from the repo folder
  python lab/discover_sources.py                  ask all prompts, update the sources
  python lab/discover_sources.py --limit 3        quick test with the first 3 prompts
  python lab/discover_sources.py --no-download    only record the sources, skip importing
  python lab/discover_sources.py --keep-old       keep pages that are no longer cited

If a run stops halfway (quota, network), run the same command again: it picks up
the unfinished run instead of starting over. Use --fresh to start over anyway.

Output, in lab/discovered/:
  sources.csv              the current sources: url, domain, how often cited, by which prompts
  changes.md               what the last update changed: new and dropped sources, top domains
  runs/<date>.jsonl        every answer of every update, with its sources (history)
And the imported pages, in lab/corpus/discovered/<domain>_<id>.md, with the same
header as fetch_sources.py, so the citation lab can use them as the competition:

  python lab/experiment.py --provider gemini --competitors lab/corpus/discovered

Needs GEMINI_API_KEY in a .env file in the repo folder (ignored by git).
Standard library only. PDF sources need:  pip install pypdf
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from fetch_sources import UA, download  # noqa: E402  (same downloader as the lab)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OUT = HERE / "discovered"
CORPUS = HERE / "corpus" / "discovered"
TARGET = "danfoss"
TRACKING = re.compile(r"^(utm_\w+|gclid|fbclid|srsltid|mc_cid|mc_eid)$", re.I)


# --- setup -------------------------------------------------------------------
def load_dotenv():
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def read_prompts(path):
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


# --- asking Gemini -----------------------------------------------------------
def ask(prompt, model, key, retries=4):
    """One grounded answer. Returns (answer text, search queries, [(uri, title, n_supports)])."""
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "tools": [{"google_search": {}}]}).encode()
    req = urllib.request.Request(API.format(model=model), data=body, headers={
        "Content-Type": "application/json", "x-goog-api-key": key})
    wait = 15
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                print(f"    busy ({e.code}), waiting {wait}s...", flush=True)
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(f"Gemini error {e.code}: {msg}")
        except urllib.error.URLError as e:
            if attempt < retries:
                print(f"    network error ({e.reason}), waiting {wait}s...", flush=True)
                time.sleep(wait)
                wait *= 2
                continue
            raise RuntimeError(f"Network error: {e.reason}")

    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    meta = cand.get("groundingMetadata", {})
    chunks = meta.get("groundingChunks", [])
    supports = collections.Counter(i for s in meta.get("groundingSupports", [])
                                   for i in s.get("groundingChunkIndices", []))
    found = [(c["web"].get("uri", ""), c["web"].get("title", ""), supports[i])
             for i, c in enumerate(chunks) if c.get("web", {}).get("uri")]
    return text.strip(), meta.get("webSearchQueries", []), found


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def resolve(uri):
    """Gemini gives Google redirect links; follow one hop to get the real page URL."""
    if "grounding-api-redirect" not in uri:
        return uri
    try:
        _opener.open(urllib.request.Request(uri, headers={"User-Agent": UA}), timeout=30)
    except urllib.error.HTTPError as e:
        if e.headers.get("Location"):
            return e.headers["Location"]
    except Exception:
        pass
    return None


def clean_url(url):
    p = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not TRACKING.match(k)]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), path,
                                    urllib.parse.urlencode(query), ""))


def domain_of(url):
    host = urllib.parse.urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def brand_of(domain):
    if TARGET in domain:
        return "Danfoss"
    parts = domain.split(".")
    main = parts[-3] if len(parts) > 2 and parts[-2] in {"co", "com", "org", "ac", "gov"} else parts[-2] if len(parts) > 1 else parts[0]
    return main.capitalize()


def page_file(url):
    slug = re.sub(r"[^a-z0-9]+", "_", domain_of(url)).strip("_")
    return CORPUS / f"{slug}_{hashlib.sha1(url.encode()).hexdigest()[:8]}.md"


# --- one update run ----------------------------------------------------------
def run_prompts(prompts, args, key):
    runs = OUT / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    partial = sorted(runs.glob("*.partial.jsonl"))
    if partial and not args.fresh:
        path = partial[-1]
        print(f"Resuming unfinished run {path.name} (use --fresh to start over)")
    else:
        for p in partial:
            p.unlink()
        path = runs / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}.partial.jsonl"

    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["prompt"]] = row

    todo = [p for p in prompts if p not in done]
    print(f"Prompts: {len(prompts)} ({len(done)} already answered, {len(todo)} to ask), "
          f"model: {args.model}\n")
    with path.open("a", encoding="utf-8") as f:
        for n, prompt in enumerate(todo, len(done) + 1):
            print(f"[{n}/{len(prompts)}] {prompt}", flush=True)
            try:
                answer, queries, found = ask(prompt, args.model, key)
            except RuntimeError as e:
                print(f"\nStopped: {e}\nProgress is saved. Run the same command again to continue.")
                sys.exit(1)
            sources = []
            for uri, title, n_sup in found:
                real = resolve(uri)
                url = clean_url(real) if real else None
                sources.append({"url": url, "title": title,
                                "domain": domain_of(url) if url else title,
                                "supports": n_sup})
            row = {"prompt": prompt, "asked_at": datetime.datetime.now().isoformat(timespec="seconds"),
                   "model": args.model, "search_queries": queries,
                   "answer": answer, "sources": sources}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            done[prompt] = row
            print(f"    {len(sources)} sources: "
                  f"{', '.join(sorted({s['domain'] for s in sources})) or 'none (answered without searching)'}")
            if args.sleep:
                time.sleep(args.sleep)

    final = path.with_name(path.name.replace(".partial", ""))
    path.rename(final)
    return final, [done[p] for p in prompts if p in done]


# --- turn the run into the current source list --------------------------------
def read_previous():
    path = OUT / "sources.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["url"]: r for r in csv.DictReader(f)}


def update_sources(rows, run_file, args):
    previous = read_previous()
    stats = {}
    for row in rows:
        for s in row["sources"]:
            if not s["url"]:
                continue
            e = stats.setdefault(s["url"], {"domain": s["domain"], "title": s["title"],
                                            "prompts": [], "supports": 0})
            if row["prompt"] not in e["prompts"]:
                e["prompts"].append(row["prompt"])
            e["supports"] += s["supports"]
    unresolved = sum(1 for r in rows for s in r["sources"] if not s["url"])

    today = datetime.date.today().isoformat()
    CORPUS.mkdir(parents=True, exist_ok=True)
    failed = []
    if not args.no_download:
        new = [u for u in stats if not page_file(u).exists()]
        print(f"\nImporting {len(new)} new pages into {CORPUS.relative_to(REPO)} "
              f"({len(stats) - len(new)} already saved)")
        for i, url in enumerate(new, 1):
            print(f"  [{i}/{len(new)}] {url}", flush=True)
            try:
                text = download(url)
            except (Exception, SystemExit) as e:  # 403s, timeouts, PDFs without pypdf...
                failed.append((url, str(e) or type(e).__name__))
                print(f"      FAILED: {failed[-1][1]}")
                continue
            words = len(text.split())
            if words < 80:
                failed.append((url, f"only {words} words (page probably needs JavaScript)"))
                print(f"      FAILED: only {words} words of text")
                continue
            brand = brand_of(stats[url]["domain"])
            style = "original" if brand == "Danfoss" else "competitor"
            page_file(url).write_text(
                f"---\nbrand: {brand}\nstyle: {style}\nurl: {url}\n"
                f"title: {stats[url]['title']}\nsource: gemini-google-search\n---\n{text}\n",
                encoding="utf-8")
            print(f"      saved {page_file(url).name} ({words} words)")

    dropped = [u for u in previous if u not in stats]
    if not args.keep_old:
        for u in dropped:
            if page_file(u).exists():
                page_file(u).unlink()

    order = sorted(stats, key=lambda u: (-len(stats[u]["prompts"]), -stats[u]["supports"], u))
    with (OUT / "sources.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "domain", "brand", "title", "prompts_citing", "supports",
                    "first_seen", "imported_file", "prompts"])
        for u in order:
            e = stats[u]
            pf = page_file(u)
            w.writerow([u, e["domain"], brand_of(e["domain"]), e["title"], len(e["prompts"]),
                        e["supports"], previous.get(u, {}).get("first_seen", today),
                        pf.relative_to(REPO).as_posix() if pf.exists() else "",
                        " | ".join(e["prompts"])])

    write_changes(rows, stats, previous, dropped, failed, unresolved, run_file, args)
    print(f"\nDone. {len(stats)} sources ({len([u for u in stats if u not in previous])} new, "
          f"{len(dropped)} dropped). See {(OUT / 'changes.md').relative_to(REPO)}")


def write_changes(rows, stats, previous, dropped, failed, unresolved, run_file, args):
    domains = collections.Counter()
    for e in stats.values():
        domains[e["domain"]] += len(e["prompts"])
    no_search = [r["prompt"] for r in rows if not r["sources"]]
    danfoss = [u for u in stats if TARGET in stats[u]["domain"]]
    new = [u for u in stats if u not in previous]

    test = f" (test run: first {args.limit} prompts only)" if args.limit else ""
    L = [f"# Source update {datetime.date.today().isoformat()}{test}", "",
         f"- Run file: `{run_file.relative_to(REPO).as_posix()}`, model `{args.model}`",
         f"- Prompts asked: {len(rows)}, answered without searching: {len(no_search)}",
         f"- Sources: {len(stats)} pages on {len(domains)} sites "
         f"({len(new)} new, {len(dropped)} dropped since the last update)",
         f"- Danfoss pages cited: {len(danfoss)}, in "
         f"{len({p for u in danfoss for p in stats[u]['prompts']})} of {len(rows)} answers", ""]
    if unresolved:
        L += [f"- {unresolved} citations could not be resolved to a real URL and were skipped", ""]
    L += ["## Most cited sites", "", "| Site | Times cited |", "|---|---|"]
    L += [f"| {d} | {n} |" for d, n in domains.most_common(25)]
    if previous:
        L += ["", f"## New sources ({len(new)})", ""] + [f"- {u}" for u in new]
        L += ["", f"## Dropped sources ({len(dropped)})", ""] + [f"- {u}" for u in dropped]
    if failed:
        L += ["", f"## Could not import ({len(failed)})", "",
              "Copy these by hand into lab/corpus/discovered/ if you need them.", ""]
        L += [f"- {u}: {err}" for u, err in failed]
    if no_search:
        L += ["", "## Answered without any source", ""] + [f"- {p}" for p in no_search]
    (OUT / "changes.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--prompts", default=str(REPO / "prompts" / "prompts.txt"))
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--limit", type=int, help="ask only the first N prompts (for testing)")
    ap.add_argument("--sleep", type=float, default=6.0,
                    help="seconds between prompts, to stay under the free per-minute limit")
    ap.add_argument("--fresh", action="store_true", help="discard an unfinished run and start over")
    ap.add_argument("--no-download", action="store_true", help="record sources, do not import pages")
    ap.add_argument("--keep-old", action="store_true",
                    help="keep imported pages that are no longer cited")
    args = ap.parse_args(sys.argv[1:])

    load_dotenv()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("No API key. Put GEMINI_API_KEY=your_key in a .env file in the repo folder.")
    prompts = read_prompts(args.prompts)[:args.limit]
    if not prompts:
        sys.exit(f"No prompts in {args.prompts}")
    if args.limit:
        args.keep_old = True  # a test run must not delete pages from the last full update
    run_file, rows = run_prompts(prompts, args, key)
    update_sources(rows, run_file, args)


if __name__ == "__main__":
    main()
