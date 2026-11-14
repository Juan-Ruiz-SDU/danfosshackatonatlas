"""
The whole process for one product, step by step:

  1. Fixed pages      download the product's fixed comparison pages (sources.txt), once
  2. Discovery        optional: ask Gemini + Google Search every question, import the pages it cites
  3. Writing          write the page in each style from the fact sheet, check for made-up numbers
  4. Citation test    for every page and question: BM25 picks the top results, an AI answers
                      from them and cites; count how often each Danfoss page gets cited
  5. Result           pick the version cited most, save it as a PDF, plus a PDF report and a ZIP

Reuses the team's code: generate_variants.py (styles, fact sheet), lab/experiment.py
(BM25, answer-box prompt, citation parsing), lab/discover_sources.py (Google Search).
"""
import collections
import csv
import datetime
import hashlib
import json
import pathlib
import random
import re
import sys
import time
import zipfile

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "lab"))
import generate_variants as gv  # noqa: E402
import experiment as lab  # noqa: E402
import discover_sources as disc  # noqa: E402

import ai  # noqa: E402
import products  # noqa: E402
import report  # noqa: E402

TARGET = "danfoss"
PUBLISHABLE = ["plain", "stats", "sources"]
STYLE_NAMES = {
    "plain": "Plain description",
    "stats": "Fact-dense (figures)",
    "sources": "Fact-dense with sources",
    "stuffed": "Keyword-stuffed (test only)",
    "original": "Danfoss's current page",
}
DEFAULTS = {
    "discovery": False, "search_model": "gemini-2.5-flash",
    "writer": "gemini", "writer_model": "gemini-2.5-flash",
    "judge": "gemini", "judge_model": "gemini-2.5-flash",
    "styles": ["plain", "stats", "sources"], "words": 400, "repeats": 1,
    "top_k": 5, "max_words": 700, "fresh_pages": False, "retries": 3,
}


def run(job, slug, settings):
    s = {**DEFAULTS, **(settings or {})}
    p = products.get(slug)
    sheet = products.fact_sheet(p)
    questions = [q["text"] for q in products.questions(p) if q["enabled"]]
    if not questions:
        raise ValueError("Select at least one question.")
    styles = [x for x in s["styles"] if x in gv.STYLES]
    if not any(x in PUBLISHABLE for x in styles):
        raise ValueError("Pick at least one style that can be published (not only keyword-stuffed).")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = p["folder"] / "runs" / stamp
    (out / "variants").mkdir(parents=True)
    (out / "settings.json").write_text(json.dumps(
        {**s, "product": p["name"], "questions": questions, "started": stamp},
        indent=2, ensure_ascii=False), encoding="utf-8")
    job.log(f"Product: {p['name']}  ·  {len(questions)} questions  ·  run folder {out.name}")

    fetch_fixed(job, p)
    discovery = discover(job, p, questions, s, out) if s["discovery"] else None

    pages = load_pages(p, s["max_words"])
    originals = [d for d in pages if d.brand.lower() == TARGET]
    competitors = [d for d in pages if d.brand.lower() != TARGET]
    for d in originals:
        d.style = "original"
    job.log(f"Comparison pages: {len(competitors)} competitor, {len(originals)} current Danfoss")
    if len(competitors) < 2:
        raise ValueError(
            f"Only {len(competitors)} competitor pages to compare against. Switch on "
            "'Find fresh sources with Google search', or add competitor links to the product.")

    variants = write_variants(job, p, sheet, styles, s, out)
    rows, summary = citation_test(job, variants + originals, competitors, questions, s, out)
    return finish(job, p, s, out, questions, variants, originals, competitors, rows, summary, discovery)


# --- 1. fixed comparison pages --------------------------------------------------
def _page_header(brand, style, url, title=""):
    return (f"---\nbrand: {brand}\nstyle: {style}\nurl: {url}\n"
            + (f"title: {title}\n" if title else "") + "---\n")


def fetch_fixed(job, p):
    rows = products.source_list(p)
    if not rows:
        return
    folder = p["folder"] / "fixed"
    folder.mkdir(exist_ok=True)
    counters, todo = {}, []
    for brand, url in rows:
        n = counters[brand] = counters.get(brand, 0) + 1
        is_danfoss = brand.lower() == TARGET
        name = f"original_{n}.md" if is_danfoss else f"{re.sub(r'[^a-z0-9]+', '_', brand.lower())}_{n}.md"
        if not (folder / name).exists():
            todo.append((brand, url, folder / name, "original" if is_danfoss else "competitor"))
    for i, (brand, url, path, style) in enumerate(todo):
        if job.cancelled():
            raise ai.Cancelled()
        job.step("Downloading the fixed comparison pages", i, len(todo))
        try:
            text = disc.download(url)
        except (Exception, SystemExit) as e:
            job.log(f"  could not download {url}: {e}")
            continue
        if len(text.split()) < 80:
            job.log(f"  skipped {url}: almost no text (page needs JavaScript)")
            continue
        path.write_text(_page_header(brand, style, url) + text + "\n", encoding="utf-8")
        job.log(f"  saved {brand}: {url}")


# --- 2. source discovery --------------------------------------------------------
def discover(job, p, questions, s, out):
    key = ai.gemini_key()
    folder = p["folder"] / "sources"
    folder.mkdir(exist_ok=True)
    found, answers = {}, []
    for i, q in enumerate(questions):
        if job.cancelled():
            raise ai.Cancelled()
        job.step("Asking Google's AI which sources it uses", i, len(questions))
        answer, queries, chunks = disc.ask(q, s["search_model"], key)
        srcs = []
        for uri, title, n_sup in chunks:
            real = disc.resolve(uri)
            if not real:
                continue
            url = disc.clean_url(real)
            e = found.setdefault(url, {"domain": disc.domain_of(url), "title": title, "questions": []})
            if q not in e["questions"]:
                e["questions"].append(q)
            srcs.append(url)
        answers.append({"question": q, "search_queries": queries, "answer": answer, "sources": srcs})
        job.log(f"  {q}  ->  {len(srcs)} sources")
        time.sleep(6)  # free per-minute limit

    with (out / "discovery.jsonl").open("w", encoding="utf-8") as f:
        for a in answers:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    def fname(url):
        slug = re.sub(r"[^a-z0-9]+", "_", disc.domain_of(url)).strip("_")
        return folder / f"{slug}_{hashlib.sha1(url.encode()).hexdigest()[:8]}.md"

    new = [u for u in found if not fname(u).exists()]
    for i, url in enumerate(new):
        if job.cancelled():
            raise ai.Cancelled()
        job.step("Importing the pages Google's AI cites", i, len(new))
        try:
            text = disc.download(url)
        except (Exception, SystemExit) as e:
            job.log(f"  could not import {url}: {e}")
            continue
        if len(text.split()) < 80:
            job.log(f"  skipped {url}: almost no text")
            continue
        brand = disc.brand_of(found[url]["domain"])
        style = "original" if brand.lower() == TARGET else "competitor"
        fname(url).write_text(_page_header(brand, style, url, found[url]["title"]) + text + "\n",
                              encoding="utf-8")

    keep = {fname(u).name for u in found}
    for f in folder.glob("*.md"):  # sources that are no longer cited
        if f.name not in keep:
            f.unlink()

    with (out / "sources.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "site", "brand", "questions_citing", "imported", "questions"])
        for url, e in sorted(found.items(), key=lambda kv: -len(kv[1]["questions"])):
            w.writerow([url, e["domain"], disc.brand_of(e["domain"]), len(e["questions"]),
                        "yes" if fname(url).exists() else "no", " | ".join(e["questions"])])
    sites = collections.Counter()
    for e in found.values():
        sites[e["domain"]] += len(e["questions"])
    job.log(f"Discovery: {len(found)} pages on {len(sites)} sites")
    return {"pages": len(found), "sites": sites.most_common(15),
            "no_sources": [a["question"] for a in answers if not a["sources"]]}


def load_pages(p, max_words):
    seen, pages = set(), []
    for d in products.page_dirs(p):
        for doc in lab.load_docs(d, "unknown", max_words):
            h = hashlib.sha1(doc.text.encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                pages.append(doc)
    return pages


# --- 3. writing -----------------------------------------------------------------
def write_variants(job, p, sheet, styles, s, out):
    kw = products.keyword(p, sheet)
    allowed = gv.norm_numbers(sheet)
    variants = []
    for i, style in enumerate(styles):
        job.step("Writing the page in different styles", i, len(styles))
        prompt = gv.PROMPT.format(topic=p["name"], words=s["words"], wiki=sheet,
                                  style=gv.STYLES[style].format(keyword=kw))
        text, attempts = generate_page(job, s, prompt)
        path = out / "variants" / f"{style}.md"
        path.write_text(text + "\n", encoding="utf-8")
        words = text.split()
        cut = " ".join(words[:s["max_words"]]) + (" ..." if len(words) > s["max_words"] else "")
        doc = lab.Doc(path, "Danfoss", style, cut)
        doc.full_text = text
        doc.unknown_numbers = sorted(gv.norm_numbers(text) - allowed, key=len)
        doc.words = len(words)
        doc.attempts = attempts
        doc.length_ok = length_ok(text, s["words"])
        variants.append(doc)
        flag = f", check numbers: {', '.join(doc.unknown_numbers)}" if doc.unknown_numbers else ""
        size = "" if doc.length_ok else ", LENGTH OFF (closest attempt kept)"
        job.log(f"  wrote {STYLE_NAMES.get(style, style)}: {len(words)} words, "
                f"{attempts} attempt(s){flag}{size}")
    return variants


def length_ok(text, target):
    """Same rule as the team's generator: within 20% of the target length."""
    return abs(len(text.split()) - target) <= 0.2 * target


def generate_page(job, s, prompt):
    """The team's length-retry generation (Pablo's generate_page): if a page is more
    than 20% off the target length, ask again telling the AI the previous word count
    and the range to hit, up to `retries` extra times, and keep the attempt closest
    to the target."""
    target = s["words"]
    lo, hi = int(0.8 * target), int(1.2 * target)
    best = last_words = None
    retries = int(s.get("retries", 3))
    for attempt in range(retries + 1):
        p = prompt
        if last_words is not None:
            p += (f"\nIMPORTANT: your previous version had {last_words} words. "
                  f"This version MUST be between {lo} and {hi} words. Aim for {target}.\n")
        page = ai.chat(s["writer"], s["writer_model"], "", p, temperature=0.3,
                       cancel=job.cancelled, use_cache=not s["fresh_pages"], log=job.log)
        page = re.sub(r"\A```(?:markdown|md)?\s*\n(.*?)\n```\s*\Z", r"\1", page.strip(),
                      flags=re.DOTALL)
        last_words = len(page.split())
        if best is None or abs(last_words - target) < abs(len(best.split()) - target):
            best = page
        if length_ok(page, target):
            return page, attempt + 1
        if attempt < retries:
            job.log(f"     attempt {attempt + 1}: {last_words} words, trying again")
    return best, retries + 1


# --- 4. citation test -------------------------------------------------------------
def citation_test(job, targets, competitors, questions, s, out):
    total = len(targets) * len(questions) * s["repeats"]
    rows, done = [], 0
    raw = (out / "citation_test.jsonl").open("w", encoding="utf-8")
    for target in targets:
        bm25 = lab.BM25(competitors + [target])  # one Danfoss page at a time vs the same rivals
        for qi, q in enumerate(questions):
            ranked = bm25.rank(q)
            rank = next(i for i, (_, d) in enumerate(ranked) if d is target) + 1
            top = [d for _, d in ranked[:s["top_k"]]]
            retrieved = target in top
            for rep in range(s["repeats"]):
                job.step("Testing which page Google's AI cites", done, total)
                seed = 42 + 1000 * rep + qi
                shown = top[:]
                random.Random(seed).shuffle(shown)
                id_to_doc = {f"D{i + 1}": d for i, d in enumerate(shown)}
                results = "\n\n".join(f"[{i}] Source: {d.brand}\n{d.text}" for i, d in id_to_doc.items())
                text = ai.chat(s["judge"], s["judge_model"], lab.SYSTEM,
                               lab.USER.format(question=q, results=results),
                               temperature=0.2, cancel=job.cancelled, log=job.log, salt=seed)
                cites, rec = lab.parse_answer(text, id_to_doc)
                mine = [c for c in cites if id_to_doc[c] is target]
                row = {
                    "page": target.name, "style": target.style, "question": q, "repeat": rep,
                    "bm25_rank": rank, "retrieved": retrieved, "in_context": target in shown,
                    "cited": bool(mine), "share": len(mine) / len(cites) if cites else 0.0,
                    "first": bool(cites) and id_to_doc[cites[0]] is target,
                    "recommended": TARGET in rec.lower(),
                    "cited_brands": [id_to_doc[c].brand for c in cites],
                    "recommendation": rec, "answer": text,
                }
                rows.append(row)
                raw.write(json.dumps(row, ensure_ascii=False) + "\n")
                raw.flush()
                done += 1
        job.log(f"  tested {STYLE_NAMES.get(target.style, target.style)} ({target.name})")
    raw.close()
    job.step("Testing which page Google's AI cites", total, total)

    summary = []
    for style in dict.fromkeys(t.style for t in targets):
        rs = [r for r in rows if r["style"] == style]
        n = len(rs)
        if not n:
            continue
        shown = [r for r in rs if r["in_context"]]
        k = sum(r["cited"] for r in rs)
        lo, hi = lab.wilson(k, n)
        summary.append({
            "style": style, "name": STYLE_NAMES.get(style, style),
            "publishable": style in PUBLISHABLE, "trials": n,
            "retrieved": sum(r["retrieved"] for r in rs) / n,
            "cited": k / n, "cited_low": lo, "cited_high": hi,
            "cited_when_shown": sum(r["cited"] for r in shown) / len(shown) if shown else 0.0,
            "share": sum(r["share"] for r in rs) / n,
            "first": sum(r["first"] for r in rs) / n,
            "recommended": sum(r["recommended"] for r in rs) / n,
        })
    summary.sort(key=lambda x: (-x["share"], -x["cited"], -x["first"]))
    return rows, summary


# --- 5. result --------------------------------------------------------------------
def finish(job, p, s, out, questions, variants, originals, competitors, rows, summary, discovery):
    job.step("Making the final page and the report", 0, 1)
    eligible = [x for x in summary if x["publishable"]]
    win = eligible[0]
    winner = next(v for v in variants if v.style == win["style"])
    baseline = next((x for x in summary if x["style"] == "original"), None)
    brands = collections.Counter(b for r in rows for b in r["cited_brands"])

    (out / "final_page.md").write_text(winner.full_text + "\n", encoding="utf-8")
    with (out / "scores.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    ctx = {
        "product": p["name"], "date": datetime.date.today().isoformat(), "run": out.name,
        "winner": win, "winner_numbers": winner.unknown_numbers, "winner_words": winner.words,
        "baseline": baseline, "summary": summary, "brands": brands.most_common(12),
        "total_citations": sum(brands.values()), "questions": questions,
        "competitors": sorted({d.brand for d in competitors}), "n_competitors": len(competitors),
        "n_originals": len(originals), "discovery": discovery, "settings": s,
        "variants": [{"style": v.style, "name": STYLE_NAMES.get(v.style, v.style), "words": v.words,
                      "unknown_numbers": v.unknown_numbers, "attempts": v.attempts,
                      "length_ok": v.length_ok} for v in variants],
        "winner_length_ok": winner.length_ok,
    }
    files = {"final_md": "final_page.md"}
    try:
        report.final_page_pdf(out / "final_page.pdf", winner.full_text, p["name"])
        report.report_pdf(out / "report.pdf", ctx)
        files.update(final_pdf="final_page.pdf", report_pdf="report.pdf")
    except ImportError:
        job.log("PDFs skipped: run  pip install fpdf2  and run again. The Markdown files are ready.")
    except Exception as e:  # noqa: BLE001  (a layout problem must not lose the whole run)
        job.log(f"Could not make the PDFs ({e}). The Markdown files are ready.")
    (out / "report.md").write_text(report.report_markdown(ctx), encoding="utf-8")
    files["report_md"] = "report.md"

    with zipfile.ZipFile(out / "all_results.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file() and f.name != "all_results.zip":
                z.write(f, f.relative_to(out).as_posix())
    files["zip"] = "all_results.zip"

    result = {
        "run": out.name, "product": p["name"], "slug": p["slug"],
        "winner": {"style": win["style"], "name": win["name"], "share": win["share"],
                   "cited": win["cited"], "first": win["first"]},
        "baseline": ({"share": baseline["share"], "cited": baseline["cited"]} if baseline else None),
        "check_numbers": winner.unknown_numbers, "files": files,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    job.step("Done", 1, 1)
    job.log(f"Best version: {win['name']} (citation share {win['share']:.0%})")
    return result
