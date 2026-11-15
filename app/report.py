"""
The two PDFs a run hands over: the final page (the winning version, ready to use)
and the report (why it won). Needs:  pip install fpdf2
"""
import pathlib
import re

FONT_SETS = [  # regular, bold, italic, bold italic: a Unicode font so ™, ₂, – print correctly
    ("C:/Windows/Fonts", "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    ("/System/Library/Fonts/Supplemental", "Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf",
     "Arial Bold Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
     "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
]
LATIN1 = {"™": "(TM)", "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
          "≈": "~", "×": "x", "₂": "2", "•": "-", "→": "->", "≤": "<=", "≥": ">="}
SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "01234567890123456789")
ACCENT = (200, 16, 46)      # Danfoss-like red for the headline numbers
BAR = (42, 111, 219)
GREY = (110, 110, 110)


def pct(x):
    return f"{100 * x:.0f}%"


def _pdf_class():
    from fpdf import FPDF  # ImportError is handled by the caller

    class PDF(FPDF):
        def __init__(self, title):
            super().__init__(format="A4")
            self.doc_title = title
            self.set_margins(20, 18, 20)
            self.set_auto_page_break(True, 18)
            self.fam, self.uni = "helvetica", False
            for folder, *names in FONT_SETS:
                paths = [pathlib.Path(folder) / n for n in names]
                if all(p.is_file() for p in paths):
                    for style, path in zip(("", "B", "I", "BI"), paths):
                        self.add_font("Body", style, str(path))
                    self.fam, self.uni = "Body", True
                    break

        def t(self, s):
            s = str(s).translate(SUBSCRIPTS)  # Arial has no ₂: CO₂ -> CO2
            if self.uni:
                return s
            for a, b in LATIN1.items():
                s = s.replace(a, b)
            return s.encode("latin-1", "replace").decode("latin-1")

        def footer(self):
            self.set_y(-12)
            self.set_font(self.fam, "", 8)
            self.set_text_color(*GREY)
            self.cell(0, 6, self.t(f"{self.doc_title}  ·  page {self.page_no()}"), align="C")
            self.set_text_color(0, 0, 0)

        def text_block(self, text, size=11, style="", h=None, color=(0, 0, 0)):
            self.set_font(self.fam, style, size)
            self.set_text_color(*color)
            self.multi_cell(0, h or size * 0.52, self.t(text), markdown=True, align="L",
                            new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)

        def heading(self, text, size=15):
            self.ln(3)
            self.set_font(self.fam, "B", size)
            self.multi_cell(0, size * 0.5, self.t(plain(text)), align="L", new_x="LMARGIN", new_y="NEXT")
            self.ln(1.5)

        def bullet(self, text, mark="•", size=11):
            self.set_font(self.fam, "", size)
            self.set_x(self.l_margin + 3)
            self.cell(6, size * 0.52, self.t(mark))
            self.multi_cell(0, size * 0.52, self.t(inline(text)), markdown=True, align="L",
                            new_x="LMARGIN", new_y="NEXT")

        def grid(self, rows, widths=None, size=9):
            if not rows:
                return
            from fpdf.fonts import FontFace
            n = max(len(r) for r in rows)
            rows = [list(r) + [""] * (n - len(r)) for r in rows]
            self.ln(1)
            self.set_font(self.fam, "", size)
            self.set_fill_color(255, 255, 255)   # colours left over from the bar chart
            self.set_draw_color(205, 205, 205)
            self.set_text_color(0, 0, 0)
            kw = {"col_widths": widths} if widths else {}
            head = FontFace(emphasis="BOLD", fill_color=(242, 242, 242))
            with self.table(text_align="LEFT", line_height=size * 0.55, headings_style=head,
                            first_row_as_headings=True, **kw) as table:
                for r in rows:
                    row = table.row()
                    for c in r:
                        row.cell(self.t(plain(str(c))))
            self.ln(3)

        def bars(self, items, label_w=62, bar_w=90):
            """Horizontal bar chart: items = [(label, 0..1, highlight)]."""
            self.set_font(self.fam, "", 9)
            for label, value, hi in items:
                y = self.get_y()
                self.set_x(self.l_margin)
                self.cell(label_w, 7, self.t(label))
                self.set_fill_color(235, 235, 235)
                self.rect(self.l_margin + label_w, y + 1.5, bar_w, 4, style="F")
                self.set_fill_color(*(ACCENT if hi else BAR))
                if value > 0:
                    self.rect(self.l_margin + label_w, y + 1.5, max(0.8, bar_w * value), 4, style="F")
                self.set_x(self.l_margin + label_w + bar_w + 2)
                self.set_font(self.fam, "B" if hi else "", 9)
                self.cell(15, 7, pct(value), new_x="LMARGIN", new_y="NEXT")
                self.set_font(self.fam, "", 9)
            self.ln(2)

    return PDF


# --- Markdown helpers -------------------------------------------------------------
def plain(s):
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    return re.sub(r"(\*\*|__|`|\*)", "", s).strip()


def inline(s):
    """Markdown inline -> fpdf2 markup (**bold**, __italic__); links show their address."""
    s = s.replace("--", "–").replace("__", "**")
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*(?!\*)", r"__\1__", s)  # *italic*
    s = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"__\1__", s)
    if s.count("**") % 2:
        s = s.replace("**", "")
    if s.count("__") % 2:
        s = s.replace("__", "")
    return s


def render_markdown(pdf, md):
    lines = md.splitlines()
    para, i = [], 0

    def flush():
        if para:
            pdf.text_block(inline(" ".join(para)), 11, h=6)
            pdf.ln(2)
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            flush()
            pdf.heading(m.group(2), {1: 20, 2: 15, 3: 13}.get(len(m.group(1)), 12))
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?\s*:?-{3,}", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            pdf.grid(rows)
            continue
        m = re.match(r"^\s*([-*+]|\d+[.)])\s+(.*)", line)
        if m:
            flush()
            mark = m.group(1) if m.group(1)[0].isdigit() else "•"
            pdf.bullet(m.group(2), mark)
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            flush()
            pdf.ln(2)
            i += 1
            continue
        para.append(line.strip().lstrip(">").strip())
        i += 1
    flush()


# --- the two PDFs -------------------------------------------------------------------
def final_page_pdf(path, md, product):
    PDF = _pdf_class()
    pdf = PDF(product)
    pdf.add_page()
    render_markdown(pdf, md)
    pdf.output(str(path))


def report_pdf(path, c):
    PDF = _pdf_class()
    pdf = PDF(f"Citation report · {c['product']}")
    pdf.add_page()
    w, b = c["winner"], c["baseline"]
    n_q = len(c["questions"])

    pdf.text_block("CITATION REPORT", 9, "B", color=GREY)
    pdf.heading(c["product"], 18)
    pdf.text_block(f"{c['date']}  ·  run {c['run']}", 9, color=GREY)
    pdf.ln(4)

    pdf.set_fill_color(248, 240, 241)
    pdf.set_draw_color(*ACCENT)
    y = pdf.get_y()
    pdf.rect(pdf.l_margin, y, pdf.epw, 34, style="DF")
    pdf.set_xy(pdf.l_margin + 5, y + 4)
    pdf.set_font(pdf.fam, "", 10)
    pdf.cell(0, 5, pdf.t("Best version to publish"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 5)
    pdf.set_font(pdf.fam, "B", 16)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 9, pdf.t(w["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(pdf.l_margin + 5)
    vs = f" Danfoss's current page: {pct(b['share'])}." if b else ""
    pdf.set_font(pdf.fam, "", 10)
    pdf.multi_cell(pdf.epw - 10, 5, pdf.t(
        f"Citation share {pct(w['share'])}: of all sources the AI cited, this share was this page.{vs} "
        f"Cited in {pct(w['cited'])} of answers, cited first in {pct(w['first'])}."),
        new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y + 38)
    pdf.set_draw_color(205, 205, 205)
    tg = c.get("targets")
    if tg:
        pdf.text_block(("Targets met. " if tg["met"] else "Targets missed: wiki suggestions are in the app. ")
                       + _check_text(tg), 10, "B" if not tg["met"] else "",
                       color=ACCENT if not tg["met"] else (0, 0, 0))
        pdf.ln(2)

    if c.get("explanation"):
        pdf.heading("What this means", 13)
        pdf.text_block(c["explanation"], 10)
        pdf.text_block(f"Written by {c['settings'].get('analyst', '')} {c['settings'].get('analyst_model', '')} "
                       "from the numbers below.", 8, color=GREY)

    pdf.heading("Ranking: best to worst", 13)
    pdf.text_block(f"Citation share per version, over {n_q} buyer questions "
                   f"× {c['settings']['repeats']} repeat(s). A tie means its 95% range overlaps the winner's.",
                   9, color=GREY)
    pdf.ln(1)
    rank = c.get("ranking") or []
    pdf.bars([(f"{r['rank']}. {r['name']}", r["share"], r["winner"]) for r in rank])

    rows = [["#", "Version", "Share", "Cited", "95% range", "Cited when shown", "Cited first", "Note"]]
    for r in rank:
        rows.append([r["rank"], r["name"], pct(r["share"]), pct(r["cited"]),
                     f"{pct(r['cited_low'])}–{pct(r['cited_high'])}", pct(r["cited_when_shown"]), pct(r["first"]),
                     "winner" if r["winner"] else "tie" if r["tie"] else ("test only" if not r["publishable"] else "")])
    pdf.grid(rows, widths=(7, 44, 13, 13, 20, 20, 16, 17), size=8)

    h = c.get("holdout")
    if h:
        pdf.heading("Holdout check: questions never used to write the pages", 13)
        verdict = ("The winner is still the most cited version" if h["winner_still_first"]
                   else "The winner is NOT the most cited version here, so its lead may come from tuning to the usual questions")
        if h["winner_beats_baseline"] is not None:
            verdict += (", and it beats Danfoss's current page." if h["winner_beats_baseline"]
                        else ", but it does not beat Danfoss's current page.")
        pdf.text_block(verdict + f" {len(h['questions'])} holdout questions.", 10)
        pdf.grid([["Version", "Share", "Cited", "95% range"]] +
                 [[x["name"], pct(x["share"]), pct(x["cited"]), f"{pct(x['cited_low'])}–{pct(x['cited_high'])}"]
                  for x in h["summary"]], widths=(80, 25, 25, 30), size=8)

    pdf.heading("Before you publish", 13)
    if c["winner_numbers"]:
        pdf.text_block(f"**Check these numbers:** {', '.join(c['winner_numbers'])}. They are in the page "
                       "but not in the fact sheet, so the AI may have made them up.", 10, color=ACCENT)
    else:
        pdf.text_block("Every number in the page is also in the fact sheet.", 10)
    target = c["settings"]["words"]
    if c.get("winner_length_ok", True):
        pdf.text_block(f"The page has {c['winner_words']} words (target {target}). "
                       "Read it once by hand before publishing.", 10)
    else:
        pdf.text_block(f"**Length:** {c['winner_words']} words, more than 20% off the target of "
                       f"{target}, even after retries. Trim it by hand if needed.", 10, color=ACCENT)
    lo_win = w.get("cited_low", 0)
    rivals = [x for x in c["summary"] if x.get("version") != w.get("version")]
    if rivals and max(x["cited_high"] for x in rivals) > lo_win:
        pdf.text_block("The 95% ranges of the versions overlap, so part of the gap may be luck. "
                       "Add questions or repeats for a firmer answer.", 10, color=GREY)

    pdf.heading("Who the AI cites", 13)
    total = c["total_citations"] or 1
    pdf.grid([["Brand", "Citations", "Share"]] +
             [[bname, n, pct(n / total)] for bname, n in c["brands"]], widths=(80, 40, 40))

    if c["discovery"]:
        d = c["discovery"]
        pdf.heading("Sources Google's AI used", 13)
        pdf.text_block(f"{d['pages']} pages were found and imported as the competition.", 10)
        pdf.grid([["Site", "Times cited"]] + [[s, n] for s, n in d["sites"]], widths=(120, 40))

    pdf.heading("How this was tested", 13)
    s = c["settings"]
    for line in [
        f"Pages written by **{s['writer']} / {s['writer_model']}** from the product fact sheet, in "
        f"{len(c['variants'])} styles.",
        f"Each page competed with {c['n_competitors']} competitor pages "
        f"({', '.join(c['competitors'][:12])}). A search ranking ("
        + {"passage": "BM25 over passages cut at the headings",
           "hybrid": "words + meaning: BM25 and nomic-embed-text embeddings, merged"}
          .get(s.get("retrieval"), "BM25 over whole pages")
        + f") picked the top {s['top_k']} results for each question, as Google's blue links do.",
        f"**JEV ({s['judge']} / {s['judge_model']})**, a different AI than the writer, then answered each "
        "question like Google's AI Overview, using only those results, and cited them"
        + (", with brand names replaced by Brand A, B, C so brand fame could not decide." if s.get("blind") else ".")
        + (" The Danfoss page was always among the results (writing quality alone)." if s.get("force_target") else ""),
        f"Each question was asked {s['repeats']} time(s) with the results shuffled; "
        f"{s.get('variants', 1)} page(s) were written per style.",
        "**Citation share**: of all citations in an answer, how many went to the Danfoss page. "
        "**Cited when shown**: how often the page was cited when the AI saw it, which measures the writing alone.",
        "Source discovery: " + ("on, fresh sources from Google Search." if s["discovery"]
                                else "off, pages saved earlier were used."),
    ]:
        pdf.bullet(line, size=10)

    pdf.heading("Questions", 13)
    for i, q in enumerate(c["questions"], 1):
        pdf.bullet(q, f"{i}.", size=9)
    pdf.output(str(path))


def _check_text(tg):
    import analysis
    return analysis.check_text(tg)


def report_markdown(c):
    w, b = c["winner"], c["baseline"]
    L = [f"# Citation report: {c['product']}", "", f"{c['date']} · run {c['run']}", "",
         f"**Best version to publish: {w['name']}**, citation share {pct(w['share'])}, "
         f"cited in {pct(w['cited'])} of answers"
         + (f" (Danfoss's current page: {pct(b['share'])})." if b else "."), "",
         ]
    if c.get("explanation"):
        L += ["## What this means", "", c["explanation"], ""]
    s = c["settings"]
    L += ["## Ranking: best to worst", "",
          f"JEV (the judge): {s['judge']} {s['judge_model']}"
          + (" · brand names hidden" if s.get("blind") else "") + f" · {s['repeats']} repeat(s). "
          "A tie means its 95% range overlaps the winner's.", "",
          "| # | Version | Share | Cited | 95% range | Cited when shown | Cited first | Note |",
          "|---|---|---|---|---|---|---|---|"]
    for r in c.get("ranking") or []:
        L.append(f"| {r['rank']} | {r['name']} | {pct(r['share'])} | {pct(r['cited'])} | "
                 f"{pct(r['cited_low'])}–{pct(r['cited_high'])} | {pct(r['cited_when_shown'])} | {pct(r['first'])} | "
                 + ("winner" if r["winner"] else "tie" if r["tie"] else "test only" if not r["publishable"] else "") + " |")
    h = c.get("holdout")
    if h:
        L += ["", "## Holdout check", "",
              f"{len(h['questions'])} questions never used to write the pages. The winner is "
              + ("still first" if h["winner_still_first"] else "**not** first") + ".", "",
              "| Version | Share | Cited | 95% range |", "|---|---|---|---|"]
        L += [f"| {x['name']} | {pct(x['share'])} | {pct(x['cited'])} | {pct(x['cited_low'])}–{pct(x['cited_high'])} |"
              for x in h["summary"]]
    if c.get("targets"):
        tg = c["targets"]
        L += ["", ("**Targets met.** " if tg["met"] else "**Targets missed:** wiki suggestions are in the app "
               "and in wiki_suggestions.md. ") + _check_text(tg)]
    if c["winner_numbers"]:
        L += ["", f"**Check these numbers before publishing:** {', '.join(c['winner_numbers'])}"]
    L += ["", "## Questions", ""] + [f"{i}. {q}" for i, q in enumerate(c["questions"], 1)]
    return "\n".join(L) + "\n"
