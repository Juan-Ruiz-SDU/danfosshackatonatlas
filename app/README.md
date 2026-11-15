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

By default everything runs on **Ollama** (`qwen3:8b`), so it uses no tokens or quota. Ollama can run
on your own computer or on the team server. To use the team server, open **Settings**, type its address
in the Ollama row (for example `http://10.126.128.116:11434/`) and press **Save address**. You must be
on the same Wi-Fi. If the address changes, ask the server's owner to run `ipconfig`.

A Gemini key is only needed for **Find fresh sources**, because that step searches Google and a local
model can't. Gemini can also be picked as the writer or judge if you want faster runs. You can get a
free key at https://aistudio.google.com/apikey. Keys are saved in `.env`, which is never committed.

Ollama on a CPU is slow: about 7 minutes per page, and 1–2 minutes per test answer. The time estimate
above the Run button includes this. Tick fewer questions for a quick run.

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

## Web page tab: your own copy of the Danfoss page

1. **Make the copy (once).** Atlas reverse-engineers the current Danfoss page, from the first Danfoss
   link of the product. It reads the page the way a crawler does, without running JavaScript, and saves:
   - `webpage/original.md` and `original.json`: a snapshot of the page as it was (the reference), with
     the crawler checks of the live page. These include status, redirects, response time, robots.txt
     and sitemap.
   - `webpage/page.md`: **your copy**, already laid out for crawlers:
     - one H1
     - real headings instead of bold text and skipped levels
     - lists and tables
     - title, description and address in the lines between `---` at the top
   Headings with nothing under them in the HTML are left out and listed. On the live page a script
   fills them.
   After this, Danfoss's site is not downloaded again. If its bot protection blocks the download,
   Atlas says so and keeps your copy. You can also save the page from your browser (Ctrl+S) and
   import the file.
2. **Adapt your copy** in the tab's editor, or in `page.md` directly. Atlas compares it with Danfoss's
   page and lists the words and numbers you added or removed. It warns about new numbers that are not
   in the wiki.
3. On every save Atlas writes:
   - `rebuilt.html`: your copy as a light static page with Product and breadcrumb JSON-LD and no
     scripts;
   - `sitemap.xml` (see `wiki/guidelines/sitemap.md`);
   - the citation test copy, style `restructured`. It is extracted the same way as Danfoss's page,
     so every run in the Run tab also scores it.
4. It shows, side by side with Danfoss's page:
   - the headings
   - crawler checks
   - what Googlebot sees: the passages AI search would cut, and which one answers each question
   - BM25 per question: whole page and best passage
   - the never-claim screen

Committed: `original.md`, `original.json`, `page.md`, `rebuilt.html`, `sitemap.xml`.
Not committed: `cache/` (the downloaded HTML). Copy again only to renew the reference. Tick
"Also replace my edited copy" only to start your copy over.

## Product by product tab

The product list is the first table in the fact sheet with a "Models" column. For Micro Plate that is
the 11 heat pump platforms. Rows of other tables with the same first column, such as the per-model
pressure table, are added to the matching product. Pick a product to build its page:

- **Page from the fact sheet**: every sentence is copied from the wiki and laid out by
  `wiki/guidelines/page-structure.md`. Nothing can be invented.
- **Rewrite with the writer AI**: the AI chosen in the Run tab rewrites that product's facts. Atlas flags
  numbers that are not in the product's facts and never-claim words.

Each page gets the same crawler checks, Googlebot view and BM25 table. Files:
`products/<name>/webpage/products/<product>.html`.

## Search ranking: whole pages or passages

Under **More options**, *Search ranking* chooses how the citation test picks the top results.

- **Whole pages**: the original lab. The AI sees each page's first words.
- **Passages**: like AI search. Pages are cut at their headings, a page ranks by its best passage,
  and the AI sees its best passages.
- **Words + meaning**: BM25 and embeddings, which match by meaning, each rank the whole pages,
  and the two rankings are merged. A page that answers the question in other words can still
  make the top results. The AI sees the same text as with *Whole pages*, so comparing the two
  shows what the ranking alone changes. It needs the `nomic-embed-text` model on the Ollama
  server (`ollama pull nomic-embed-text`, already installed on the team server). Embeddings are
  saved in `app/cache/embeddings/`, so each page is only processed once.

Scores from different settings are not comparable.

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
| `products/<name>/webpage/` | Web page tabs: `page.md` (your copy), `original.md/.json` (reference), `rebuilt.html`, `sitemap.xml`, `products/*.html`, `cache/` (not committed) |
| `wiki/guidelines/` | How pages are written and laid out. Instructions for the writer, not facts |
| `questions/standard.json` | Standard questions for all products |
| `app/providers.json` | The AIs the app can use |
