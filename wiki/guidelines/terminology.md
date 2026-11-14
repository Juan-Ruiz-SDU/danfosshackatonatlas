---
type: Guideline
title: Terminology
description: Buyer wording and spelling variants that BM25 and search engines treat as different words.
tags: [guideline, terminology, bm25, keywords]
applies_to: writer
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T19:30:00Z
---
# Why
The lab's BM25 ranking and keyword-based search match words, not meanings. The lab review found that "double-wall" and "double wall" do not match each other, so a page that only uses one form loses questions written with the other.

# Use the buyer's words, in both forms where buyers use both
- brazed plate heat exchanger, and the short form BPHE
- double wall and double-wall
- heat pump, heat pumps
- R290 and propane (the residential propane heat pump brochure uses both)
- condenser, evaporator: name the duty the model is for
- low-GWP refrigerants: list the refrigerant names from the fact sheet

# Do not
- Do not repeat a phrase to push the ranking (keyword stuffing). BM25 gives almost nothing for extra repeats, and Google's spam policies cover it.
- Do not explain an abbreviation (for example SGHX) unless the fact sheet explains it. Write model names exactly as in the fact sheet.
