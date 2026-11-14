---
type: Guideline
title: Evaluation hygiene
description: Rules that keep the citation lab honest - no copying test questions, holdout questions, no keyword stuffing.
tags: [guideline, experiment, citation lab]
applies_to: writer
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T19:30:00Z
---
# Rules
- Headings name topics in the buyer's words. They never copy the lab's test questions (lab/questions.txt) word for word: a page tuned to the exact test questions wins the test without being a better page.
- After a round of changes, also run the lab on lab/questions_holdout.txt. If Danfoss only improves on the regular questions, the change is learning the test.
- Compare results only with runs made under the same lab settings. Changing the ranking (for example plural matching, or whole pages versus passages) starts a new series.
- The keyword-stuffed style is a negative control for the lab, never a page to publish.
- A reformatted page and the page it comes from must hold the same words and the same numbers; the app checks this before the reformatted page enters the lab.
