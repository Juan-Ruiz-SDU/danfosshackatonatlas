# Atlas

Atlas finds the version of a product page that AI search cites most. Examples of AI search are Google's AI Overviews and Gemini.
It does four things:

1. It writes the page in several styles, using only the product's wiki as the source of facts.
2. It tests every version in a simulated answer engine against real competitor pages, with a judge AI called **JEV**.
3. It ranks the versions from best to worst and hands you the winning page and a report.
4. When a target is missed, it proposes wiki changes for a person to accept or decline.

It also keeps a working copy of a section of danfoss.com, which the team edits page by page for crawlers and AI search.

Atlas was built by a Danfoss hackathon team, and the first products are Danfoss heat exchangers and motor protectors. Everything runs on your own computer.

- `app/README.md` holds the detailed user guide.
- `lab/README.md` describes the command-line citation lab.
- `ANALYSIS.md` covers the features and a critical review of the app's weak points, and what has been fixed since.

## Status: set up for more data, not yet re-run

We did not have time to run the tests again with more data. Atlas is now set up so the next run uses it.
By default a run uses the **Thorough** preset:

- all buyer questions are ticked (15 standard questions per product, up from 1 for Micro Plate and 5 for the motor protector);
- every question is asked 3 times, with the results shuffled;
- 2 pages are written per style;
- the best versions are re-tested on holdout questions that were never used to write the pages: 10 for Micro Plate, 5 for the motor protector;
- the judge (JEV) is a different AI from the writer, and it does not see brand names.

The results shown today, including the Micro Plate training round in `wiki/guidelines/competitor-training.md`, were measured with less data. Run again with the Thorough preset before you present results as firm. The **Quick** preset (1 pass, 1 page per style, no holdout) is still there for trying things out.

---

## Start

You need Python 3.10 or later.

```bash
pip install -r requirements.txt      # once: fpdf2 (PDFs), pypdf (PDF brochures), matplotlib (lab chart)
python Run.py app                    # or double-click "Start Atlas.bat"
```

The app opens at `http://127.0.0.1:8765`. Only your computer can reach it. Keep the terminal window open while you use it.

### AI models: three roles, kept apart

| Role | Default | Why |
|---|---|---|
| **Writer** (writes the pages) | Ollama `qwen3:8b` | Free and local. Set its address in ⚙ Settings (your computer or the team server). |
| **JEV, the judge** (plays Google's answer box and cites sources) | Gemini `gemini-2.5-flash` | Must be a **different AI than the writer**. A model prefers text in its own style, so a run refuses to start if the two are the same. Any other Ollama model also works. |
| **Explainer** (writes the text about the result and the wiki suggestions) | Ollama `qwen3:8b` | It only turns numbers into plain language, so a small local model is enough. |
| Source discovery (Citations tab, "Find fresh sources") | Gemini with Google Search | A free key from https://aistudio.google.com/apikey, saved in ⚙ Settings. |
| Embeddings for the section writer (optional) | Ollama `nomic-embed-text` | `ollama pull nomic-embed-text` |
| Grounding checker for the fact check (optional) | Ollama `bespoke-minicheck` | `ollama pull bespoke-minicheck` (check its licence) |

"JEV" is the name the lab already used for its reviewer (`lab/review.py`). In the app it is the judge role.

- **Other AIs:** any OpenAI-compatible chat API can be added in ⚙ Settings › Add an AI, and is stored in `app/providers.json`.
- **Keys and settings:** stored in `.env`, which is never committed.
- **Saved answers:** every AI answer is saved in `app/cache/`, so running the same step again is free and an interrupted run continues where it stopped.

---

## The interface

- **Navigation rail (left):** Overview, Run, Web page, Model by model, Citations, Wiki, How it works.
- **Sub-tabs:** each tab is split into sub-tabs, so no view is one long page.
- **Links to views:** the address bar shows the current view, so any view can be linked or bookmarked. Examples:
  - `#web/structured`
  - `#run/questions-detail`
  - `#overview:micro-plate-bphe`, which also picks the product.
- **Alert dot:** a red dot on Citations means there are unread alerts.

**Header:**

| Control | What it does |
|---|---|
| Product picker and **+** | Pick the product. **+** adds a product from a brochure; the AI drafts the fact sheet and you check it before saving. |
| **Go to… (Ctrl K or /)** | Command palette: jump to any view or product, or open settings, the assistant, the presentation or the theme. |
| Screen icon | **Presentation mode**: a seven-step guided tour for the pitch. Use ←/→ or Space, and Esc to end. |
| Half-circle icon | Theme: automatic, light or dark. |
| **Assistant** | A chat docked on the right (team Ollama server). It knows the app, the current view and the product's facts. |
| Gear | Settings: API keys, AIs, default citation targets, standard questions, **alerts by email**. |

### Overview

The headline for the jury:

- **Rank per buyer question, before and after.** Danfoss's page (as copied) against your edited copy, among the saved competitor pages, by best passage or whole page.
- **Readouts:**
  - the latest run's citation share and how often it is cited first;
  - the holdout check;
  - whether the targets were met;
  - Gemini's real citations of Danfoss;
  - the size of the test.
- **Charts:** run by run, and what Gemini really cites over time.

### Run: write and test page versions

| Sub-tab | What you do there |
|---|---|
| 1 Product | Product type and main use (they fill the standard questions), comparison pages (competitor links and the current Danfoss page), and the fact sheet. |
| 2 Buyer questions | Tick the standard questions and this product's own questions. **Holdout questions** are listed separately: standard ones from `questions/holdout.json`, plus this product's own. They are only used to check the best versions. |
| 3 Run | **How much data** (Quick / Thorough), the writer, JEV, the explainer, the page styles, citation targets, and more options. Press **Run**. |
| 4 Results | The **text about the result**, the **ranking from best to worst (up to 10)** with ties marked, the **holdout check**, the downloads (final page PDF/Markdown, report PDF, everything as ZIP), and wiki suggestions if a target was missed. |
| Per question | A heatmap of how often JEV cited each version for each question. Click a cell to read **JEV's real answers**, with the brand labels it saw. |
| Versions | Every page written in the run, side by side, with numbers that are not in the fact sheet flagged. |

**More options:**

- words per page;
- repeats per question;
- pages per style;
- search results JEV sees;
- length retries;
- words of each page JEV reads;
- search ranking (whole page or passages);
- holdout check;
- hide brand names from JEV;
- always show the Danfoss page to JEV, which tests the writing alone;
- embeddings for the section writer;
- write brand-new pages.

**What a run does** (`app/pipeline.py`):

1. **Comparison pages.** It downloads the listed competitor pages into `products/<slug>/fixed/`. If **Find fresh sources** is on, it also asks Gemini with Google Search every question and imports the pages it cites into `sources/`. Pages that are no longer cited are removed on purpose: each update of the wiki starts from the latest citations.
2. **Writing.** The writer writes N pages per style from the wiki. The styles are:
   - plain description;
   - fact-dense;
   - fact-dense with sources;
   - section by section with verified citations (one page);
   - keyword-stuffed, a negative control for testing only.

   A page more than 20% off the target length is asked again. Numbers that are not in the fact sheet are flagged. `1.5` and `15` count as different numbers.
3. **Citation test.** For every version, every question and every repeat:
   - BM25 ranks the version against the competitor pages;
   - the top results go, shuffled, to **JEV**. With brands hidden it sees "Brand A/B/C", and brand names in the text are masked too;
   - JEV answers like an AI Overview and cites `[D1]`, `[D2]`, and so on.
4. **Ranking.** Versions are sorted by citation share. The result keeps the top 10, and a version is a **tie** when its 95% range of "cited" overlaps the winner's. The best publishable version wins.
5. **Holdout check.** The two best publishable versions and Danfoss's current page are asked the holdout questions. If the winner is not first there, its lead may come from tuning to the usual questions.
6. **Text about the result.** The explainer writes 4 to 6 sentences from the numbers only: who won and by how much, whether the gap is firm, what the holdout says, and what to do next.
7. **Files.** `final_page.pdf/.md`, `report.pdf/.md` (ranking, holdout, text, method), `scores.csv`, `citation_test.jsonl`, `citation_holdout.jsonl`, `all_results.zip`.
8. **Targets and wiki analysis.** If the winner misses the product's targets, the explainer compares the best and worst versions and proposes wiki changes. Nothing changes until a person accepts.

### Web page: your copy of Danfoss's website

| Sub-tab | What it shows |
|---|---|
| Site | **Copy the website** (with and without JavaScript), the copies as a small website, the authority checks, and **⬇ The whole website (ZIP)**: every page, `sitemap.xml`, `robots.txt`. |
| Edit | The page copy in Markdown. `{{wiki: path#Section}}` lines are filled from the wiki whenever the site is built. |
| Before / after | A slider over Danfoss's page (snapshot) and your copy (the two scroll together), the word and number changes, headings before and after, and the never-claim screen. |
| Competitors | Rank per question against the competitor pages, the buyer's words your page lacks, and the wiki blocks that contain them. |
| Fact check | Every claim checked against the wiki, `raw/` documents and Danfoss's pages. |
| Crawlers | Crawler checks and the passages Googlebot would cut. |
| **Structured data** | The page's **schema.org JSON-LD** and checks of what Google reads from it, with a copy button and a link to Google's Rich Results Test. |
| BM25 | Rank per question, Danfoss's page against your copy. |

**Structured data:** every built page carries JSON-LD in its `<head>`, built from the page and the wiki only.

| Page | What its JSON-LD says |
|---|---|
| Catalog (most tiles lead to pages below it) | A `CollectionPage` with the list of its products. |
| Product or technology | A `Product`, with Danfoss as brand and manufacturer and the product type as category. On model pages (Model by model) it also carries the model and its specifications from the fact-sheet table. |
| Service, partner or news | A `WebPage` about Danfoss. |

Every page also has a `WebPage` and breadcrumbs. Prices, reviews and ratings are never invented. Google needs them for product rich snippets, so they can only come from a real Danfoss price list or real reviews.

### Model by model

- **Models** lists the product family's models, from the first fact-sheet table with a "Models" column.
- **Model page** builds a page for one model, either from the fact sheet alone or rewritten by the writer. It gets the crawler checks, structured data, Googlebot view, BM25 table and fact check.

### Citations: what Gemini really cites

| Sub-tab | What it does |
|---|---|
| 1 Ask Gemini | Asks the prompts in `prompts/prompts.txt` with Google Search on. Records Gemini's searches, the pages it cites and each page's share of the answer, and imports those pages. |
| 2 Over time | One row per update: Danfoss's share, the most cited sites, the targets, and a chart. |
| 3 Answers | Per prompt: the sources and their shares, and how our page ranks for each of Gemini's searches. An AI reviewer explains why those pages were cited and can suggest wiki changes. |
| **Alerts** | When to test again (see below). |

### Alerts: a new model, or a change in how Google ranks pages

AI models are renewed often, and each one knows the web only up to a date. Google also changes how pages earn authority. Either can make today's results stale. `app/watch.py` reads **Google News** (public RSS, no key) every 24 hours, starting a minute after Atlas starts, and whenever you press **Check the news now**. It raises two kinds of alert:

- **New model:** a Gemini model newer than the ones Atlas uses appears in the news. With a Gemini key, Atlas also reads Google's official model list and warns about model names it has not seen. The alert says the pages probably need a new round of tests, and how.
- **Ranking and authority:** news about Google core or spam updates, E-E-A-T, site reputation, AI Overviews or AI Mode. The first check only learns what is already out there; later checks alert on new stories.

Each alert shows in the app (a banner and the red dot) and is **sent by email** in a direct tone: what happened, why it matters, what to do, with the sources.

- **Recipient:** for now it is the invented address `atlas-alerts@example.com`. `example.com` is reserved, so nothing is delivered, and each email is saved as a `.eml` file in `app/outbox/`.
- **To receive them:** open ⚙ Settings › Alerts by email, set a real address and an SMTP server (host, port 587 or 465, user, password, from), and press **Send a test email**.
- **Other settings there:** how often to check, and an optional automatic refresh of the Citations tab every N days (uses Gemini quota; 0 = off).

On 15 Nov 2026 the first check already found Gemini 4 and other 3.x models in the news, while Atlas is set up with `gemini-2.5-*`. Adding a newer model in Settings and re-testing is the next step.

### Wiki: the facts every page uses

| Sub-tab | What it does |
|---|---|
| Edit | Every wiki file with its type and the website pages that use it. Edit a file or create a new concept. A save does four things: it checks that the whole wiki still loads the way the writer loads it (otherwise nothing is saved), flags **new numbers** (each needs a Danfoss source), notes the change in `log.md`, and rebuilds the website copy so pages with wiki blocks follow. |
| Change log | `log.md`, newest first: edits made here, accepted suggestions and the team's own notes. |
| Original documents | The Danfoss documents the wiki cites and whether each is saved in `raw/`. **Download missing documents** runs `lab/fetch_raw.py`. |

### How it works

What the section-by-section writer did in a run, in four sub-tabs:

- **The process:** the flow with counts and the citation precision.
- **Sub-queries:** what the page must answer.
- **Evidence:** the candidate passages and the reranker's choices.
- **Embedding map:** a 2-D map of the evidence, competitor passages, our sections and the sub-queries.

---

## Security of the local server

Atlas listens on `127.0.0.1` only. It also refuses requests that are not from its own page:

- the `Host` header must be `127.0.0.1:<port>` or `localhost:<port>` (this stops DNS rebinding);
- a request from another website (`Origin`) is refused;
- every POST must be JSON.

So a website open in the same browser cannot change keys, AI addresses or the wiki.

## Command line

```bash
python Run.py                          # write pages for Micro Plate (default product) with Ollama
python Run.py --product motorprotector # another product
python Run.py --help                   # all options of generate_variants.py
python Run.py app                      # the Atlas app
python Run.py update-sources           # ask Gemini the prompts, import the cited pages (lab/discover_sources.py)
python Run.py update-raw               # download the original Danfoss documents the wiki cites into raw/

python lab/experiment.py --provider gemini           # the citation lab (see lab/README.md)
python lab/experiment.py --force-target              # always show the Danfoss page: tests the writing alone
python lab/experiment.py --questions lab/questions_holdout.txt   # the holdout questions
python lab/review.py <normal run> <force-target run> # JEV the reviewer: why Danfoss loses, wiki gaps
```

## Where things are

| Path | What it holds |
|---|---|
| `wiki/` | The Micro Plate wiki (an OKF bundle): the only source of facts. `guidelines/` holds writing and site rules, `policies/` the never-claim and source rules, `log.md` the change log. |
| `products/<slug>/` | One product: `product.json`, `questions.json` (switched-off standard questions, its own questions, its holdout questions), `wiki/`, `fixed/` and `sources/` (comparison pages, not committed), `runs/<date>/` (results, not committed), `webpage/` (the website copy). |
| `questions/standard.json`, `questions/holdout.json` | Standard and holdout questions shared by every product. |
| `prompts/prompts.txt` | Prompts for the Citations agent. |
| `raw/` | Original Danfoss documents the wiki cites. |
| `lab/` | The command-line citation lab, the review loop (JEV the reviewer) and source discovery. |
| `app/` | The app. `server.py` (HTTP API) and `pipeline.py` (a run) are the core; `watch.py` handles the alerts and `wikiedit.py` the Wiki tab. The other modules: `ai.py`, `analysis.py`, `brochure.py`, `catalog.py`, `chat.py`, `citations.py`, `comparison.py`, `products.py`, `report.py`, `retrieval.py`, `sections.py`, `verify.py`, `webpage.py`, `website.py`. `static/` holds the interface: `index.html`, `style.css`, `app.js`, `how.js`, `overview.js`, `features.js`. |
| `app/outbox/` | Alert emails saved when no real address or SMTP server is set (not committed). |
| `app/providers.json` | The AIs the app can use. |
| `.env` | API keys, alert email and SMTP settings (never committed). |

## Changes that break comparisons (15 Nov 2026)

Runs made after these changes are a new series. Compare them only with each other.

- JEV is now a different AI from the writer, and it sees "Brand A/B/C" instead of brand names.
- Defaults are 3 repeats, 2 pages per style, and all 15 standard questions.
- Results are ranked per version (`plain_1`, `plain_2`, …), not per style.
- The number check no longer treats `1.5` and `15` as the same number.

## Limitations to keep in mind

- **A simulation, not Google.** The Run tab's test is BM25 over a few pages plus one LLM as the judge. It shows which version a model prefers among these pages, not what Google will do. The Citations tab, with Gemini's real grounding data, is the stronger evidence. Present the two together.
- **Ties are common.** Even with the Thorough preset, versions often tie. Report a tie as a tie, and trust a lead only if it also holds on the holdout questions.
- **Network and quota.** Gemini needs internet and has a free daily quota; a Thorough run can hit it, and pressing Run again the next day continues where it stopped. The copy of danfoss.com can be blocked by bot protection; you can then import a page saved from your browser.
