---
type: Guideline
title: Competitor training
description: How the web pages are improved against competitor pages - wiki blocks in the buyer's words, measured with BM25 against the saved competitor pages, checked on holdout questions.
tags: [guideline, bm25, competitors, training, web page]
applies_to: app
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T23:00:00Z
---
# How the content gets onto the web pages
- The web pages (Atlas app, Web page tab) take product facts from this wiki through **wiki blocks**: a line `{{wiki: platforms/heat-pump-platforms}}`, or `{{wiki: technologies/micro-plate-pattern#Benefits}}` for one section, in a page copy.
- Every time the website is built, each block is replaced by the wiki as it is then. This happens when the tab opens, when a page is saved, before every Run and before every `lab/experiment.py` run. **When this wiki changes, the web pages and the citation test change with it.** Nobody has to copy facts by hand.
- Footnotes, links between concepts and internal notes (for example remarks about the never-claim policy) are left out of the web page. Generic headings such as "Facts" are dropped.
- Because the content comes from here, the wording in this wiki is what BM25 and the AI read. Write facts in the buyer's words.

# How a page is trained against competitor pages
1. The Web page tab's **Against the competitors** table shows, for each buyer question:
   - where the page ranks against the saved competitor pages, by best passage and as a whole page;
   - which page beats it;
   - the question's words the winner has and our page lacks;
   - the wiki blocks that contain those words.
2. Add the wiki block under an H2 heading in the buyer's words (for example "Heat pump platforms: capacity, models and working pressure"). Never copy a competitor's text, claims or figures. Never copy the test questions as headings.
3. Measure again on the regular questions **and** on `lab/questions_holdout.txt`. Keep a change only if the holdout questions improve too, or at least do not get worse.
4. When no wiki block has the missing words, the gap is in this wiki, not on the page. Add the fact here, with its Danfoss source, and the page picks it up.

# First training round (Micro Plate page, 2026-11-14)
The page gained eight wiki blocks:
- product overview
- heat pump platforms and pressures
- refrigerants and charge (Micro Plate pattern benefits, Z-design, mixing chamber)
- double wall
- HEXSelector
- Application Development Centers

It also gained H2 headings in buyer words. All of Danfoss's text stayed. BM25 against the 6 saved competitor pages (Alfa Laval, SWEP, Hexonic):

| Question set | Whole page, mean rank | Best passage, times ranked first |
|---|---|---|
| lab/questions.txt (12) | 2.50 → 1.67 | 4 → 10 of 12 |
| Atlas standard questions (15) | 3.80 → 3.20 | 5 → 9 of 15 |
| Holdout (5, never used for training) | 3.80 → 2.20 | 1 → 2 of 5 |

Questions still lost need facts this wiki does not have yet:
- maintenance and cleaning
- lifetime
- where to buy (distributors)
- cost (never a price, see the never-claim policy)
- energy efficiency figures (only with a Danfoss source)

These are BM25 results, not AI citations. Confirm them with a Gemini run of the citation lab before telling the jury.

# Limits
- BM25 matches words, not meaning. "double-wall" and "double wall", or "energy-efficient" and "energy efficient", are different words to it. Use both forms (see [Terminology](terminology.md)).
- A longer page is not automatically better: BM25 corrects for length, and the lab cuts pages to 700 words in whole-page mode. Put the most useful sections early.
- Danfoss's own text on the page still contains claims the never-claim policy does not allow ("outperforms", "unparalleled", "Up to 10%"). The Web page tab lists them; removing them is a team decision.
