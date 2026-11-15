# Atlas: features to add and a critical review

Written 2026-11-15 after reading the whole code base. It covers `Run.py`, `generate_variants.py`, `app/`, `app/static/` and `lab/`.
Part A lists what the code can already do but the app does not show yet, plus new features that build on it.
Part B is a calibrated review of what can go wrong. Each item is labelled:

- **Confirmed:** read in the code, with a concrete trigger.
- **Plausible:** depends on the environment or the data.
- **Methodology:** the code works, but the claim drawn from it may be stronger than the evidence.

## Status after the second pass (15 Nov 2026)

| Item | Status |
|---|---|
| B2.3 Small n, no holdout | **Done.** The "Thorough" default uses 3 repeats, 2 pages per style and all 15 standard questions. A holdout re-test of the best versions is on by default. The result is a ranking (top 10) with ties marked. **The tests have not been re-run with more data yet**: everything is set up for the next run. |
| B2.1 Same model writes and judges | **Done.** The judge is now "JEV", by default Gemini 2.5 Flash. A run refuses to start if JEV is the writer's model. The text about the result is written by a third role, the explainer (qwen3:8b). |
| B2.2 Judge sees brands | **Done.** "Hide brand names from JEV" is on by default: Brand A/B/C labels, and brand names in the text are masked. |
| B1.1 Discovery deletes pages | **Accepted by design** (team decision). Each wiki update starts from the latest citations, so old sources may go. |
| B1.2 1.5 = 15 | **Fixed** in `generate_variants.norm_number` and `verify._numbers`. Thousands separators are still ignored. |
| B1.4 "Recommended" | **Fixed:** it matches the page's brand or its blind label as a word. |
| B4.1 Cross-site requests | **Fixed:** checks on `Host`, `Origin` and JSON-only POSTs. Tested: text/plain, a foreign Origin and a foreign Host get 403. |
| B5.2 CSS collision | **Fixed** in the redesign. |
| A1 #1, 2, 4, 5, 6, 7, 8, 9 | **Done:** holdout, force-target option, per-question heatmap, JEV's real answers, versions side by side, a raw/ download button, more run settings, the change log (Wiki tab). |
| A2 #11, 12, 13, 14, 15, 17, 18 | **Done:** brand-blind JEV, separate judge, ties, JSON-LD structured data (Product / CollectionPage / WebPage), website ZIP export, scheduled Citations refresh (optional), wiki editor. |
| New: alerts | **Done:** news watch for new Gemini models and Google ranking/authority changes, with alert emails (invented address until set; saved to `app/outbox/`). |
| A1 #3 Review loop in the app, A2 #16 Offline demo mode | **Not done.** `lab/review.py` still runs from the command line only. |
| B2.4–B2.8, B3.1–B3.5 | **Open.** BM25 is still the retrieval stand-in. The fact check still counts Danfoss pages as a source. Stop still waits for the current call. There are still no automated tests. |

---

## Part A: features to add

### A1. Already in the code base, missing or hidden in the app

| # | Feature | Where it lives today | Value | Effort |
|---|---|---|---|---|
| 1 | **Holdout check.** Re-test the winning page on questions the loop never saw. | `lab/questions_holdout.txt`. The lab README describes the protocol, but the Run tab cannot do it. | High. It is the only defence against "learning the test" (see B2.3). | S: one more question set and a second score column. |
| 2 | **"Cited when shown" / force-target run.** Always show the Danfoss page to the judge, so the score measures writing quality alone. | `lab/experiment.py --force-target` | High. It separates *retrieval* losses from *writing* losses. | S |
| 3 | **Review loop: why Danfoss loses.** It separates wording losses (BM25: missing buyer words) from content losses (shown, but a rival was preferred), and finds wiki gaps. | `lab/review.py` (CLI only) | High. It is a much richer diagnosis than the Run tab's best-vs-worst analysis. | M: run it as a job and render `REVIEW.md`. |
| 4 | **Per-question results.** A heatmap of style × question showing cited, first and who won instead. | Data already in `runs/<run>/citation_test.jsonl` | High for the pitch. It shows *where* the page wins. | S |
| 5 | **Real AI answers in the UI.** Read the judge's answer for any trial. | `citation_test.jsonl` → `answer` | Medium. The lab README itself says "quote a real AI answer in the pitch". | S |
| 6 | **All variants of a run, side by side**, with word count, length check and flagged numbers. | `runs/<run>/variants/*.md` (only in the ZIP today) | Medium | S |
| 7 | **Update the original sources (`raw/`)** with one button, plus a status of which wiki sources have a raw copy. | `python Run.py update-raw` (`lab/fetch_raw.py`) | Medium. The fact check and the section writer depend on `raw/`. | S |
| 8 | **Hidden run settings.** These are in `pipeline.DEFAULTS` but not in the UI: `max_words`, embeddings on/off, embedding model, reranker and analyst model, passage size and passages per page. | `pipeline.DEFAULTS`, `experiment.py --passage-words/--passages` | Low to medium (power users) | S |
| 9 | **Wiki change log viewer.** Every accepted suggestion is written to `wiki/log.md`, but the app never shows it. | `analysis._log` | Medium. It gives an audit trail for the jury. | S |
| 10 | **Run-over-run trend** of the Run tab's winner share and target status. | `citations.lab_history` already computes it. It is only drawn on the Citations chart. | Medium | S |

### A2. New features that build on what exists

| # | Feature | Why | Effort |
|---|---|---|---|
| 11 | **Brand-blind judge option.** Send "Source: Brand A/B/C" instead of the real names (see B2.2). | Removes the judge's brand bias from the headline metric. | S: `pipeline.citation_test`, one setting. |
| 12 | **Separate judge model by default**, or a warning when writer = judge. | Self-preference bias (B2.1). | S |
| 13 | **Significance on the winner.** Show "tied with X" when the 95% ranges overlap, instead of naming one winner. | B2.3 | S: Wilson ranges are already computed. |
| 14 | **JSON-LD `Product` schema** generated from the fact sheet for every product page. | `webpage.audit` already checks JSON-LD; it could generate it too. | M |
| 15 | **Export the mini website** as a static ZIP (HTML, sitemap.xml, robots.txt) to hand to the web team. | Turns the Web page tab into a deliverable. | S |
| 16 | **Offline demo mode** using the lab's `fake` provider, or cached answers only. | A jury demo must not depend on Wi-Fi or the team Ollama server. | S to M |
| 17 | **Scheduled citation updates** (weekly), with a "what changed" digest. | `discover_sources` already writes `changes.md`. | M |
| 18 | **Wiki editor with source links.** Edit a concept and see which pages and claims use it. | The wiki is the single source of truth, but it can only be edited outside the app. | M to L |

**Top 5 by value per effort:** 1 (holdout), 4 (per-question heatmap), 13 (winner significance), 11 (brand-blind judge), 2 (force-target).

---

## Part B: critical review

Severity scale:

- **High:** can give a wrong headline result or lose work.
- **Medium:** wrong in some cases, or a real but conditional security risk.
- **Low:** cosmetic, rare, or easy to notice.

### B1. Correctness and data loss

**B1.1 Discovery deletes competitor pages of questions not in the current run.** *Confirmed · Medium*

- **Where:** `app/pipeline.py`, `discover()`, lines 179-182. After a Run with "Find fresh sources" on, every `products/<slug>/sources/*.md` that was not cited *in this run* is deleted.
- **Trigger:** tick 3 of 15 questions and run with discovery. The competitor pages imported earlier for the other 12 questions are removed. The same happens if Gemini returns no sources for a question that day (for example a quota hiccup).
- **Impact:** later runs compete against fewer, different pages. Results then change for reasons that have nothing to do with the page. Getting the pages back costs Gemini quota.
- **Fix:** only delete when every question was asked and answered. Otherwise keep the old pages, as `citations.update` already does with `keep_old`.

**B1.2 Number check treats `1.5` and `15` as the same number.** *Confirmed · Medium*

- **Where:** `generate_variants.norm_numbers()` removes `.` and `,` so that "1,200" equals "1200". That also makes "1.5" equal "15", and "0.5" equal "05"/"5".
- **Trigger:** the fact sheet says "15 bar" and a page says "1.5 bar". The number is not flagged.
- **Impact:** a shifted decimal point is a very common way for an AI to invent a number, and this is the main guard against invented numbers in the Run tab. `app/verify.py` `_numbers()` does the same: tested, `"15 bar"` and `"1.5 bar"` both give `{'15'}`. So the fact check's number step misses it too.
- **Fix:** only strip separators when they sit between groups of three digits (thousands). Keep decimal points.

**B1.3 Partial Citations updates rewrite `sources.csv` with only the subset.** *Confirmed · Low*

- **Where:** `lab/discover_sources.update_sources()`. Asking one prompt section rewrites `lab/discovered/sources.csv` with only that section's sources. The next full update compares against that subset, so pages dropped earlier are never cleaned up, and `first_seen` dates are lost.
- **Fix:** merge with the previous CSV when `keep_old` is on.

**B1.4 "Recommended" counts any answer that mentions Danfoss.** *Confirmed · Low*

- **Where:** `pipeline.citation_test`, `TARGET in rec.lower()`.
- **Trigger:** "Not Danfoss: pick SWEP" counts as recommending Danfoss.
- **Impact:** only the secondary "recommended" metric, not the winner.

**B1.5 The section writer's own sources count as invented numbers.** *Confirmed · Low*

- **Where:** the "Section by section" style cites `raw/` passages (`[r12]`), but `allowed_numbers()` only allows numbers from the fact sheet.
- **Impact:** correct numbers taken from the original brochures are shown as "check these numbers". This is a false alarm, not a missed error.

**B1.6 GET `/api/site` writes files.** *Confirmed · Low*

- **Where:** `site_state()` calls `website.refresh()`, which rebuilds the whole mini website and the lab copy on every open of the tab.
- **Impact:** a run that is reading the same files at that moment can see half-written pages. It is rare, but GET requests should not write.

### B2. Methodology: how much the citation test proves

**B2.1 The same model writes and judges by default.** *Methodology · High*

- **Where:** `pipeline.DEFAULTS` sets both writer and judge to `ollama / qwen3:8b`.
- **Why it matters:** models tend to prefer text in their own style (self-preference bias). The winner may be "the page qwen likes", not "the page Google cites".
- **Fix:** default the judge to a different model family, or at least warn when they are equal. Report results with two judges.

**B2.2 The judge sees the brand names.** *Methodology · Medium*

- **Where:** `pipeline.citation_test` shows each result as `[D3] Source: Danfoss`.
- **Why it matters:** brand recognition can push citations up or down for reasons the page text does not control.
- **Fix:** add a brand-blind option (A2 #11). Note that the Citations tab's AI reviewer already masks brands.

**B2.3 The winner is picked on a small, noisy sample, and on the same questions it was tuned for.** *Methodology · High*

- **Where:** the winner is `summary[0]` by point estimate of the share (`pipeline.citation_test` / `finish`).
- **Sample size:** with the default 1 repeat and, say, 6 ticked questions, each style has 6 trials. The 95% Wilson range for 3/6 is about 19%–81%. Two styles at 50% and 33% are statistically indistinguishable, yet one is named "best version".
- **Overfitting:** the wiki-suggestion loop then tunes the wiki to the same questions. Improvement on those questions is expected even if the pages are not better in general. The holdout set exists in `lab/` but not in the app (A1 #1).
- **Fix:** show a tie when the ranges overlap. Recommend at least 2 repeats and 10 questions before a claim to the jury. Report holdout results.

**B2.4 BM25 over a handful of pages stands in for Google retrieval.** *Methodology · Medium*

- **Why it matters:** with about 6 competitor pages and top-5, almost every page is "retrieved", so the retrieval filter barely discriminates. The team noted this itself.
- **Implications:**
  - Format-only changes barely move whole-page BM25. That is an honest finding, not a bug.
  - Passage mode is closer to AI search, but it is still not Google.
- **Fix:** present results as "in a simulated answer engine". The Citations tab (real Gemini grounding) is the stronger evidence. Present the two together.

**B2.5 Re-running gives the same answers, not new evidence.** *Methodology · Low*

- **Where:** answers are cached by prompt and seed (`ai.chat`).
- **Why it matters:** pressing Run again with the same settings reproduces the result exactly, which is good for reproducibility. It is not a confirmation, though. Only "repeats" (new seeds) or "Write brand-new pages" add samples.

**B2.6 The fact check partly checks Danfoss against itself.** *Methodology · Medium*

- **Where:** `verify.evidence_units` includes the snapshots of Danfoss's own pages (`webpage/site/*/original.md`).
- **Why it matters:** any claim copied from danfoss.com passes as "copied from a source", so "supported" means "matches Danfoss's marketing", not "backed by a document". The never-claim screen catches some of this, but not wrong facts.
- **Fix:** show the source type per verdict (wiki / raw document / Danfoss page) and count Danfoss-page-only support separately.

**B2.7 Self-verification in the section writer.** *Methodology · Low to medium*

- **Where:** the writer model also checks its own sentences unless Bespoke-MiniCheck is installed.
- **Mitigation:** the mandatory exact quote and `quote_supports()` limit the risk. Even so, a "citation precision 1.0" from the same model is weaker evidence than it looks.

**B2.8 Small-n agreement score in the Citations reviewer.** *Methodology · Low*

- **Where:** a Spearman correlation over 3 to 6 passages.
- **Why it matters:** values of ±1 happen by chance often. The UI should show n next to it, or hide it below about 5 pages.

### B3. Robustness

**B3.1 Stop is slow on a CPU.** *Confirmed · Low.* `ai.chat` only checks the stop flag between calls, and a call can take up to 30 minutes (`timeout=1800`). The UI says "Stopping after the current step", which is honest, but a page on a CPU takes about 7 minutes. Streaming (as `ollama_stream` already does for the analysis) would make Stop immediate.

**B3.2 Citations update captures all printing in the process.** *Confirmed · Low.* `contextlib.redirect_stdout` is global, so while an update runs, prints from other threads (another job, a server traceback) land in the Citations log.

**B3.3 Default Ollama address is a team-server IP.** *Confirmed · Low (UX).* `app/providers.json` ships with `http://10.126.128.116:11434/`. A new laptop off that Wi-Fi sees "Ollama can't be reached" on the first start. The banner explains it, but `localhost` would be a safer default.

**B3.4 Long brochures are cut silently.** *Confirmed · Low.* `brochure_limit()` sends at most 30,000 characters (Ollama) or 60,000 (others). Facts after that point never reach the draft, and the user is not told.

**B3.5 No automated tests.** *Confirmed · Medium for a fast-moving team.* There are no tests in the repo. B1.1 and B1.2 are the kind of regressions a handful of unit tests would catch: `norm_numbers`, `parse_answer`, `discover` keep/delete, `md_to_items`/`items_to_md` round trip.

### B4. Security of the local server

**B4.1 Any web page in the browser can change Atlas's settings.** *Plausible · Medium*

- **Where:** `app/server.py` listens on `127.0.0.1` but checks neither the `Origin` nor the `Host` header. `Handler.body()` parses any POST body as JSON, whatever its `Content-Type`.
- **Trigger:** while Atlas runs, a malicious page can send a "simple" cross-site POST (`text/plain`) to `http://127.0.0.1:8765/api/provider/update` to point the Gemini provider at its own server. The next Gemini call then sends `Authorization: Bearer <GEMINI_API_KEY>` there. The same route can overwrite keys (`/api/key`) or accept wiki suggestions.
- **Mitigation:** recent Chrome versions ask before public sites reach local addresses (Local Network Access). Other browsers may not, and DNS rebinding bypasses origin checks unless `Host` is validated.
- **Fix (small):**
  - reject POSTs whose `Content-Type` is not `application/json`;
  - reject requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, or whose `Origin` is set to anything else.

**B4.2 Path handling is sound.** *Checked.* `/files/`, `/pages/` and `/static/` resolve paths and require them to stay inside their root. Product slugs and run names are validated. No issue found.

### B5. UX

- **B5.1 Very long tabs.** The Web page tab stacks 10 cards and the Run tab 5. This is addressed by the new sub-tab layout (see README, "The interface").
- **B5.2 CSS collision.** *Confirmed · Low.* A late `.qlist { padding-left: 22px }` rule meant for the How it works tab also indented the Run tab's question lists. Fixed in the redesign.
- **B5.3 Jargon on the first screen.** "BM25", "RRF" and "sub-queries" appear without a plain explanation on first use. The How it works tab explains them, but the Overview should lead with outcomes.

**Top 5 risks to fix first:** B2.3 (winner on small n and no holdout), B2.1 (same model writes and judges), B1.1 (discovery deletes pages), B1.2 (decimal-point numbers pass the check), B4.1 (cross-site POSTs to the local server).
