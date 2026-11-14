# Citation lab

Checks whether the rewritten Danfoss pages (`variants ManuJuan/`) get cited by an
AI answer engine more than Danfoss's original pages, when they compete with real
competitor pages (from `DataNatalia/`).

It simulates Google's two filters for every Danfoss page and every buyer question:

1. **Retrieval**: BM25 ranks the page against the competitor pages; only the top 5 go on.
2. **AI answer**: an LLM (Gemini Flash, or Qwen3 in Ollama) answers using only those 5
   results and cites them `[D1]`, `[D2]`... Results are shuffled on every repeat so
   position doesn't decide.

Each style (plain, stats, original...) then gets a score: how often the page was
retrieved, cited, cited first and recommended, plus its citation share.

## Files

| File | What it is |
|---|---|
| `sources.txt` | Pages to download: Danfoss originals + direct rivals (Alfa Laval, SWEP, Hexonic, CIAT) |
| `questions.txt` | 12 neutral buyer questions. Edit freely |
| `fetch_sources.py` | Downloads `sources.txt` into `corpus/` as clean text |
| `experiment.py` | Runs the lab and writes `results/<date>/` |
| `corpus/` | The downloaded pages (commit them, so everyone tests the same corpus) |
| `cache/` | Saved AI answers, so re-runs don't spend quota (not committed) |
| `results/` | One folder per run: `summary.md`, `summary.csv`, `chart.png`, `trials.jsonl` |

## Run it

From the repo folder:

```bash
pip install pypdf matplotlib          # PDFs and the chart; everything else is standard library

python lab/fetch_sources.py           # 1. download competitor + Danfoss original pages
python lab/experiment.py --provider fake --limit-questions 2   # 2. test the plumbing (free, random answers)
python lab/experiment.py --provider gemini                     # 3. the real run
```

For the Gemini run, put your key in a `.env` file in the repo folder (it's ignored by git):

```
GEMINI_API_KEY=your_key_here
```

The full run is 5 variants + the originals × 12 questions × 2 repeats ≈ 170 answers.
At the free tier's per-minute limit that takes roughly 20 minutes. If the daily
quota runs out, run the same command again tomorrow: cached answers are reused and
it picks up where it stopped.

Useful options:

```bash
--styles plain,stats      only some styles
--repeats 3               more repeats = tighter confidence ranges
--force-target            always show the Danfoss page to the AI: tests the writing alone
--provider ollama --model qwen3:8b   private, local, no key
--model gemini-2.5-flash-lite        a different Gemini model
```

## Changes that break comparisons

- **2026-11-14, plural stemming in BM25.** `tokens()` in `experiment.py` now maps plurals
  to singular (pumps → pump, manufacturers → manufacturer, batteries → battery; nothing
  more aggressive). This changes which pages make the top 5, so **results from before
  this fix are not comparable with results after it**. The round-1 folders
  `results/2026-11-14_164814_gemini` and `results/2026-11-14_170322_gemini` are from
  before the fix, and so is the review in `review/2026-11-14_173157`. Compare new runs
  only with runs made after the fix.

## Reading the result

- **Citation share** is the headline number.
- **Cited when shown** isolates writing quality from retrieval.
- **95% range**: if two styles' ranges overlap a lot, the gap may be luck. Add
  repeats or questions before telling the jury one style wins.
- `trials.jsonl` keeps every answer, so you can quote a real AI answer in the pitch.

When Manu and Juan generate new styles (`sources_1.md`, `stuffed_1.md`...), just run
the experiment again: styles are read from the file names.

## Review loop: why does Danfoss lose?

After a normal run and a `--force-target` run, `review.py` works out why Danfoss
lost and writes proposals for a person to approve:

```bash
py lab/review.py lab/results/<normal run> lab/results/<force-target run> --sleep 0
```

1. **Wording losses** (plain code): the Danfoss page never made BM25's top 5. Lists
   the buyer words from the question that the page lacks, and which rival pages have them.
2. **Content losses**: the page was shown (taken from the `--force-target` run) but a
   competitor was preferred. A reviewer model ("JEV") compares the winning competitor
   page with the Danfoss page and ranks the differences. It only describes differences
   and never states Danfoss facts.
3. **Wiki check**: for each difference, does the wiki already have the information?
   Yes → a **generator problem** (fix `generate_variants.py`). No → a **wiki gap**,
   proposed in `WIKI_PROPOSALS.md` and marked **NEEDS DANFOSS SOURCE**. The code checks
   that every wiki line the model quotes really exists.

Output goes to `lab/review/<date_time>/`: `REVIEW.md` (everything, ranked),
`WIKI_PROPOSALS.md` (approve/reject one by one) and `review.json`. The script never
edits the wiki. A person adds approved facts with their Danfoss source, following
`wiki/policies/`. Then regenerate the variants and run the lab again.

It reuses the provider options and answer cache of `experiment.py` (`--provider`,
`--model`, `--host`, `--sleep`). By default it uses the model of the runs.
`--provider fake` tests the plumbing offline.

**Holdout:** `questions_holdout.txt` holds 5 questions the loop never sees. After a
round of fixes, run the lab on them too (`--questions lab/questions_holdout.txt`). If
Danfoss only improves on the 12 regular questions, the fixes are learning the test,
not making better pages.
