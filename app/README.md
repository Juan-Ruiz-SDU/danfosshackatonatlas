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

## Web page tab: your own copy of Danfoss's website

1. **Copy the website (once).** Give the first page of a section of danfoss.com. For Micro Plate that is
   the heat exchanger catalog (`site_start` in `product.json`). Atlas follows the links in the pages'
   content that stay inside that section, up to two clicks deep and the number of pages you choose. It
   always includes the product's own Danfoss page. Every page is read twice:
   - without JavaScript, the way many crawlers see it;
   - with JavaScript, in Edge or Chrome without a window, the way a visitor sees it.

   For each page Atlas saves a snapshot as the reference (`site/<page>/original.md` and `.json`) and
   **your copy** (`site/<page>/page.md`), already laid out for crawlers. Copying again only renews
   the snapshots, unless you tick "Also replace my edited copies".

   danfoss.com cannot be shown inside Atlas: its server forbids being framed (`X-Frame-Options`). If its
   bot protection blocks a download, Atlas says so. You can save that page from your browser and import it.
2. **Your website** shows the copies as a small website that looks like Danfoss's: header, menu,
   breadcrumbs, catalog tiles and footer. The links between the pages work. Click through it, or pick a
   page in the list. The list shows how deep each page is and how many pages link to it and from it.
   **How the website spreads authority** checks the whole site against `wiki/guidelines/site-structure.md`:
   - pages a crawler cannot reach from the first page;
   - orphan pages;
   - pages more than 3 clicks deep;
   - the sitemap;
   - Danfoss pages whose text needs JavaScript.
3. **Product facts come from the wiki.** In a page copy, a line `{{wiki: platforms/heat-pump-platforms}}`
   (or `{{wiki: technologies/micro-plate-pattern#Benefits}}` for one section) is replaced by that part of the
   wiki whenever the website is built:
   - when the tab opens;
   - when a page is saved;
   - before every Run;
   - before every `lab/experiment.py` run.

   When the team changes the wiki, the web pages and the citation test change with them. Pick blocks from
   the list under the editor.
   **Against the competitors** shows, for each question:
   - where the page ranks against the saved competitor pages;
   - which page beats it;
   - the question's words it lacks;
   - the wiki blocks that hold those words. Click one to insert it.

   See `wiki/guidelines/competitor-training.md` for the method and the first training round.
4. **Edit the page** in Markdown. Catalog tiles are written as `- [Title](address): description`.
   Atlas compares your copy with Danfoss's page and warns about new numbers that are not in the wiki.
5. For the page you pick it shows:
   - the headings, before and after
   - crawler checks
   - what Googlebot sees
   - BM25 per question against the competitor pages
   - the never-claim screen

   The product's own page (Micro Plate) is also the `restructured` page of the citation test.

Files in `products/<name>/webpage/`:
- committed: `site.json` (the map), `site/<page>/` (snapshot and copy), `site/<page>.html` (the
  rendered page), `sitemap.xml`;
- not committed: `cache/` (downloaded HTML).

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

## Citations tab: what Gemini with Google Search cites

The agent is `lab/discover_sources.py`, the same one `python Run.py update-sources` runs. It asks Gemini,
with Google Search on, every prompt in `prompts/prompts.txt` and keeps three things:
- the searches Gemini ran (its sub-queries);
- the pages it cited;
- how much of the answer each page supports.

It then imports those pages as text. **Update citations** runs it for one section of the prompts,
or for at most N prompts. Every update is kept in `lab/discovered/runs/`, so the tab shows how the
citations change.

- **Share of the answer.** Gemini does not use BM25 and gives no score per page. It does say which
  pieces of its answer each page supports. A page's share is the part of the answer it supports, from
  that data. Updates made before shares were recorded show support counts instead.
- **Per prompt**, the tab shows:
  - the cited pages with their shares;
  - Gemini's searches;
  - for each search, where the chosen page of ours ranks among the cited pages' passages (BM25) and who leads.
  "Our pages" are the website copy, the last Atlas run and the newest variants. The wiki is not used here.
- **Explain why** asks an AI reviewer (the Run tab's answer-box AI) to score the cited passages and ours
  on checkable signals: direct answer, figures with units, named models, definition or comparison,
  scope, self-contained. It then explains the result. Every passage is plain text of the same length,
  with brand names hidden and the order shuffled, so markdown and length cannot count. The reviewer's
  totals are compared with Gemini's real shares (rank correlation), so you can see whether the reviewer
  judges like the engine.
- AI Overviews has no public API. Reading it needs a paid search-results service (for example SerpApi or
  DataForSEO).

## Fact check

**Check every claim** (Web page tab) and **Fact check this page** (Product by product) check each sentence,
list item and table row. The sources are the wiki, the original documents in `raw/` and Danfoss's page
snapshots. The checks run in this order:
1. A claim copied from a source passes at once.
2. Every number must appear in the best-matching source.
3. The rest goes to a grounding checker: Bespoke-MiniCheck-7B if it is installed in Ollama
   (`ollama pull bespoke-minicheck`; check its licence for commercial use). Otherwise the Run tab's
   answer-box AI checks it, and must quote the exact supporting words. The quote is verified in code.

See `app/verify.py`.

## Search ranking: whole pages or passages

Under **More options**, *Search ranking* chooses how the citation test picks the top results.

- **Whole pages**: the original lab. The AI sees each page's first words.
- **Passages**: like AI search. Pages are cut at their headings, a page ranks by its best passage,
  and the AI sees its best passages.

Scores from the two settings are not comparable.

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
| `products/<name>/webpage/` | Web page tab: `site.json`, `site/<page>/page.md` (your copies), `original.md/.json` (references), `site/*.html`, `sitemap.xml`; `products/*.html` (product pages); `cache/` (not committed) |
| `wiki/guidelines/` | How pages are written and laid out. Instructions for the writer, not facts |
| `questions/standard.json` | Standard questions for all products |
| `app/providers.json` | The AIs the app can use |
