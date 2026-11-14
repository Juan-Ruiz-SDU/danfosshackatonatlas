# Writing guidelines
How generated pages are built. These files are instructions, not facts: they are kept out of the fact sheet, and their numbers never count as allowed facts. `applies_to: writer` guidelines go into the writer prompt; `applies_to: app` ones are checked by the Atlas app's code (Web page tab).

* [Page structure](page-structure.md) - One H1, one section per buyer topic, self-contained passages, specs in tables.
* [Crawlability](crawlability.md) - What Googlebot and AI search need from the HTML: content in the first response, a fast and error-free server, clean metadata.
* [Sitemap](sitemap.md) - Every published page is listed in an XML sitemap with its final address and the date it last changed, so Google finds it and reads it again after changes.
* [Terminology](terminology.md) - Buyer wording and spelling variants that BM25 and search engines treat as different words.
* [Evaluation hygiene](evaluation-hygiene.md) - Rules that keep the citation lab honest: no copying test questions, holdout questions, no keyword stuffing.
