# Atlas app

Atlas finds the version of a product page that AI search cites most, and gives you that page as a
PDF, along with a PDF report that explains why it won.

## Start

Double-click **`Start Atlas.bat`**, or from the repo folder run:

```bash
pip install -r requirements.txt   # once
python Run.py app
```

It opens in your browser at `http://127.0.0.1:8765`. Only your own computer can reach it. Keep the
black window open while you use it.

The first time, Atlas asks for a Gemini API key. You can get a free one at
https://aistudio.google.com/apikey. The key is saved in `.env`, which is never committed.

## What happens when you press Run

1. **Product**: pick a product, or add one from a brochure (PDF, Word or text). The AI pulls the
   facts out of the brochure, and you check and correct them before anything is written.
2. **Questions**: the standard questions are shared by every product. `{product}`, `{a_product}` and
   `{application}` are filled in from each product. You can untick any of them for one product, add
   questions for one product only, or add new standard questions for all products.
3. **Find fresh sources** is off by default, so runs are faster and use the comparison pages saved
   earlier. When it's on, Atlas asks Gemini with Google Search every question and imports the pages
   it cites as the competition.
4. Atlas writes the page in each style (plain, fact-dense, with sources) from the fact sheet, and
   flags any number that isn't in the fact sheet.
5. Every version competes with the competitor pages and Danfoss's current page. A search ranking
   picks the top results, then an AI answers like Google's AI Overview and cites its sources.
6. The version with the highest citation share wins. You can download:
   - **Final page (PDF)**: the winning version
   - **Report (PDF)**: scores of every version, who the AI cites, numbers to check, how it was tested
   - **Everything (ZIP)**: all versions, every AI answer, the sources and the scores

Answers are saved in `app/cache/`. If a run stops because of the free daily limit, press Run again
the next day and it continues where it stopped, without spending the quota again.

## Adding another AI

Open **Settings > Add an AI**. Any service with an OpenAI-compatible chat API works: OpenAI, Mistral,
Azure OpenAI, LM Studio, or an internal Danfoss model. You can also edit `app/providers.json` directly.
Source discovery always uses Gemini, because it reports which Google Search pages it used.

## Files

| Where | What |
|---|---|
| `products/<name>/product.json` | Name, product type, main use, search phrase |
| `products/<name>/wiki/` | The fact sheet. The Micro Plate product uses the repo's `wiki/` |
| `products/<name>/questions.json` | Questions switched off for this product, and its own questions |
| `products/<name>/sources/`, `fixed/` | Comparison pages: discovered, and from the fixed link list |
| `products/<name>/runs/<date>/` | Each run's results (not committed) |
| `questions/standard.json` | Standard questions for all products |
| `app/providers.json` | The AIs the app can use |
