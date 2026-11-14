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

## Reading the result

- **Citation share** is the headline number.
- **Cited when shown** isolates writing quality from retrieval.
- **95% range**: if two styles' ranges overlap a lot, the gap may be luck. Add
  repeats or questions before telling the jury one style wins.
- `trials.jsonl` keeps every answer, so you can quote a real AI answer in the pitch.

When Manu and Juan generate new styles (`sources_1.md`, `stuffed_1.md`...), just run
the experiment again: styles are read from the file names.
