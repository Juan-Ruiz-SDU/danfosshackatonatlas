# Directory Update Log

## 2026-11-14
* **Policy change** (approved by the team): `policies/source-of-truth.md` now allows any official Danfoss document or danfoss.com page, each cited with its document code (or URL) and date. Competitor material is never a source. The eBrochure AD565353287087en-000101 stays the main source. Descriptions in `policies/index.md`, `references/index.md` and `references/danfoss-bphe-ebrochure.md` updated to match.
* **Creation**: `references/danfoss-r290-ebrochure.md`, the Danfoss eBrochure "Danfoss brazed plate heat exchangers" for residential propane heat pumps (AD501740144629en-000102, PDF file dated 2024-10-04). Same title as the main eBrochure but a different document.
* **Update** (approved by the team; proposals from the lab review `lab/review/2026-11-14_175811`): facts added, each with its own footnote:
  * `services/hexselector.md`: six lines on applications, latest product range, registration, updates and web address (danfoss.com Micro Plate page, accessed 2026-11-14; brochure AD138986468027en-000301, PDF file dated 2025-03-11).
  * `platforms/heat-pump-platforms.md`: max. working pressure for H39L-EZU, H62L-CZ, HDW30-C and HDW44-C (danfoss.com news 2024-09-30; data sheet AI356147463903en-000101, 2022.07).
  * `products/micro-plate-bphe-heat-pumps.md`: one line pointing to the per-model pressure table.
  * `technologies/double-wall-option.md`: four lines on the double wall models and design, and one line on their main application in heat pump systems for hot sanitary water (AD501740144629en-000102, pages 9-11).
  * Not added, no Danfoss source found: HEXSelector calculation modes, languages and cross-reference tools; an overall max. pressure for the heat pump range. Left out on purpose: the Hexact tool (2022 data sheet, may be outdated) and the "L = 45/49 bar" type-code rule (would be an inference for other models). Marketing claims and percentages in the sources were not copied (see `policies/never-claim.md`).
* **Update**: Removed the old single-file `wiki.md`; this bundle is now the only fact sheet. The pages from the generation run started at 12:27 UTC with the previous script (`variants/<style>_1.md` to `<style>_3.md`) were generated from that `wiki.md` and are kept to show progress. Pages numbered after them come from this bundle.
* **Creation**: Converted the single-file fact sheet `wiki.md` into this OKF v0.2 bundle (one concept per file, provenance in frontmatter). No facts added or removed. Awaiting human review: no concept has `verified` yet.
