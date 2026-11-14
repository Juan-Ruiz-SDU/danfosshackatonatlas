# Citation lab review (2026-11-14_173157)

- Run `lab/results/2026-11-14_164814_gemini`: normal, `gemini/gemini-3.6-flash`, 144 trials
- Run `lab/results/2026-11-14_170322_gemini`: --force-target, `gemini/gemini-3.6-flash`, 144 trials
- Reviewer: `gemini/gemini-3.6-flash`
- Content losses taken from: the --force-target run (page always shown)

## Summary

- **Wording losses** (Danfoss page not in BM25's top 5): 6 questions
- **Content losses** (shown, but a competitor was preferred): 8 questions, 6 where a rewritten variant lost
- **Generator problems** (the wiki has it, the variants leave it out): 7
- **Wiki gaps** (proposals in WIKI_PROPOSALS.md, all NEEDS DANFOSS SOURCE): 6

## 1. Wording losses

The page never reached the AI. Fix by using the buyer's words (only where the wiki supports the topic). Ranked by share of trials lost.

| # | Question | Lost | Pages not found (rank) | Buyer words missing from the page |
|---|---|---|---|---|
| W1 | Which brazed plate heat exchanger brand do you recommend for a heat pump manufacturer? | 6/12 | original_1 (#6), plain_1 (#6), plain_3 (#6) | brand (3), pump (3), manufacturer (3) |
| W2 | Copper-brazed or nickel-brazed plate heat exchanger: which supplier should I choose? | 6/12 | original_1 (#6), stats_1 (#6), stats_2 (#6) | copper-brazed (3), nickel-brazed (3), supplier (3) |
| W3 | What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump? | 4/12 | plain_1 (#6), plain_3 (#6) | condenser (2), 10 (2), kw (2), pump (2) |
| W4 | Which plate heat exchanger gives the best part-load efficiency in a variable-load heat pump? | 2/12 | original_1 (#6) | part-load, variable-load, pump |
| W5 | Who makes double-wall brazed plate heat exchangers for domestic hot water? | 2/12 | original_1 (#6) | double-wall, domestic, hot |
| W6 | Which brazed plate heat exchanger suppliers offer selection software? | 2/12 | original_1 (#6) | suppliers, selection, software |

### W1. Which brazed plate heat exchanger brand do you recommend for a heat pump manufacturer?

- **original_1** (original): rank 6, BM25 score 0.78 vs 0.95 for the last page shown (Hexonic (hexonic_2)).
  - missing `brand` (the page only has `brands`: the lab's BM25 does not match word forms): used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_1), Hexonic (hexonic_3)
  - missing `manufacturer` (the page only has `manufacturers`: the lab's BM25 does not match word forms): used by no higher page
  - question phrasing only, not worth adding: `recommend`
- **plain_1** (plain): rank 6, BM25 score 0.9 vs 0.95 for the last page shown (Hexonic (hexonic_2)).
  - missing `brand`: used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_1), Hexonic (hexonic_3)
  - missing `manufacturer` (the page only has `manufacturers`: the lab's BM25 does not match word forms): used by no higher page
  - question phrasing only, not worth adding: `recommend`
- **plain_3** (plain): rank 6, BM25 score 0.91 vs 0.95 for the last page shown (Hexonic (hexonic_2)).
  - missing `brand`: used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_1), Hexonic (hexonic_3)
  - missing `manufacturer`: used by no higher page
  - question phrasing only, not worth adding: `recommend`

### W2. Copper-brazed or nickel-brazed plate heat exchanger: which supplier should I choose?

- **original_1** (original): rank 6, BM25 score 0.51 vs 0.57 for the last page shown (Hexonic (hexonic_1)).
  - missing `copper-brazed` (the page only has `brazed`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_2)
  - missing `nickel-brazed` (the page only has `brazed`: the lab's BM25 does not match word forms): used by no higher page
  - missing `supplier`: used by no higher page
  - question phrasing only, not worth adding: `choose`
- **stats_1** (stats): rank 6, BM25 score 0.49 vs 0.57 for the last page shown (Hexonic (hexonic_1)).
  - missing `copper-brazed` (the page only has `brazed`, `copper`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_2)
  - missing `nickel-brazed` (the page only has `brazed`, `nickel`: the lab's BM25 does not match word forms): used by no higher page
  - missing `supplier`: used by no higher page
  - question phrasing only, not worth adding: `choose`
- **stats_2** (stats): rank 6, BM25 score 0.49 vs 0.57 for the last page shown (Hexonic (hexonic_1)).
  - missing `copper-brazed` (the page only has `brazed`, `copper`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_2)
  - missing `nickel-brazed` (the page only has `brazed`, `nickel`: the lab's BM25 does not match word forms): used by no higher page
  - missing `supplier`: used by no higher page
  - question phrasing only, not worth adding: `choose`

### W3. What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?

- **plain_1** (plain): rank 6, BM25 score 1.96 vs 1.97 for the last page shown (SWEP (swep_1)).
  - missing `condenser`: used by Hexonic (hexonic_3), Hexonic (hexonic_1), Alfa Laval (alfa_laval_1)
  - missing `10`: used by Hexonic (hexonic_2)
  - missing `kw`: used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_3), Hexonic (hexonic_1)
- **plain_3** (plain): rank 6, BM25 score 1.59 vs 1.97 for the last page shown (SWEP (swep_1)).
  - missing `condenser`: used by Hexonic (hexonic_3), Hexonic (hexonic_1), Alfa Laval (alfa_laval_1)
  - missing `10`: used by Hexonic (hexonic_2)
  - missing `kw`: used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_3), Hexonic (hexonic_1)

### W4. Which plate heat exchanger gives the best part-load efficiency in a variable-load heat pump?

- **original_1** (original): rank 6, BM25 score 0.79 vs 0.92 for the last page shown (Hexonic (hexonic_2)).
  - missing `part-load`: used by no higher page
  - missing `variable-load`: used by no higher page
  - missing `pump` (the page only has `pumps`: the lab's BM25 does not match word forms): used by Hexonic (hexonic_1), Hexonic (hexonic_3)
  - question phrasing only, not worth adding: `gives`

### W5. Who makes double-wall brazed plate heat exchangers for domestic hot water?

- **original_1** (original): rank 6, BM25 score 0.95 vs 2.03 for the last page shown (SWEP (swep_2)).
  - missing `double-wall`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2)
  - missing `domestic`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2), Hexonic (hexonic_1)
  - missing `hot`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2), Hexonic (hexonic_1), SWEP (swep_1), SWEP (swep_2)
  - question phrasing only, not worth adding: `makes`

### W6. Which brazed plate heat exchanger suppliers offer selection software?

- **original_1** (original): rank 6, BM25 score 0.63 vs 0.64 for the last page shown (Hexonic (hexonic_1)).
  - missing `suppliers`: used by no higher page
  - missing `selection`: used by Hexonic (hexonic_2)
  - missing `software`: used by SWEP (swep_1)
  - question phrasing only, not worth adding: `offer`

## 2. Content losses

The AI saw the Danfoss page and still preferred a competitor. Ranked by loss rate.

| # | Question | Lost | Winner (times) | Losses by style | Reviewed |
|---|---|---|---|---|---|
| C1 | Which heat exchanger helps reduce the refrigerant charge of a heat pump? | 12/12 | Alfa Laval / alfa_laval_1 (12) | original 2/2, plain 6/6, stats 4/4 | stats_1 vs alfa_laval_1 |
| C2 | Which brazed plate heat exchanger suppliers offer selection software? | 12/12 | SWEP / swep_1 (12) | original 2/2, plain 6/6, stats 4/4 | stats_1 vs swep_1 |
| C3 | Who makes double-wall brazed plate heat exchangers for domestic hot water? | 8/12 | Alfa Laval / alfa_laval_1 (8) | original 2/2, plain 4/6, stats 2/4 | stats_1 vs alfa_laval_1 |
| C4 | Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32? | 6/12 | Alfa Laval / alfa_laval_1 (6) | original 2/2, plain 4/6, stats 0/4 | plain_1 vs alfa_laval_1 |
| C5 | What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump? | 6/12 | Alfa Laval / alfa_laval_1 (5), Hexonic / hexonic_3 (1) | original 0/2, plain 6/6, stats 0/4 | plain_3 vs alfa_laval_1 |
| C6 | What is the best evaporator heat exchanger for a 100 kW commercial heat pump? | 2/12 | SWEP / swep_1 (1), Hexonic / hexonic_3 (1) | original 0/2, plain 2/6, stats 0/4 | plain_2 vs swep_1 |
| C7 | Copper-brazed or nickel-brazed plate heat exchanger: which supplier should I choose? | 2/12 | Hexonic / hexonic_2 (1), Hexonic / hexonic_3 (1) | original 2/2, plain 0/6, stats 0/4 | only the public original lost: not reviewed |
| C8 | Which brazed plate heat exchanger brand do you recommend for a heat pump manufacturer? | 1/12 | Alfa Laval / alfa_laval_1 (1) | original 1/2, plain 0/6, stats 0/4 | only the public original lost: not reviewed |

## 3. Generator problems

The wiki already has this information; the variants leave it out or bury it. Fix in `generate_variants.py` (prompt or styles). Ranked by importance.

### G1. Selection software features and capabilities

- **Questions lost:** Which brazed plate heat exchanger suppliers offer selection software?; What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Suggestion for generate_variants.py:** Mention that Danfoss provides the HEXSelector software to help select the right brazed plate heat exchanger.
- **Wiki already has** (wiki/services/hexselector.md):
  - "Danfoss HEXSelector software helps select the right brazed plate heat exchanger."
- **Evidence:**
  - stats_1 lost to SWEP (swep_1): The competitor page details two dedicated dimensioning software tools (SWEP SSP and DThermX), highlighting features such as three calculation modes (design, performance, rating), online access with no download needed, fast calculations that can be saved and shared, and multi-language support. Danfoss page: weak ("Danfoss HEXSelector software aids in selecting the appropriate heat exchanger").
  - plain_2 lost to SWEP (swep_1): the competitor page details two separate dimensioning tools (SWEP SSP and DThermX) featuring three calculation modes and replacement cross-reference tools. Danfoss page: weak ("Danfoss provides a selection tool, HEXSelector software, to help users choose the appropriate exchanger.").

### G2. Prominent section focus on charge reduction

- **Questions lost:** Which heat exchanger helps reduce the refrigerant charge of a heat pump?; What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?
- **Suggestion for generate_variants.py:** Give refrigerant charge reduction a dedicated section or heading highlighting that Micro Plate™ technology enables a lower refrigerant charge in many systems.
- **Wiki already has** (wiki/technologies/micro-plate-pattern.md):
  - "In many systems it also enables a lower refrigerant charge."
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page features a dedicated section header titled 'Reduce your charge. Increase your potential.' explicitly positioning charge reduction as a primary capability. Danfoss page: weak ("enabling lower refrigerant charges.").
  - plain_3 lost to Alfa Laval (alfa_laval_1): the competitor page states that its asymmetric channel plate engineering is built to minimize refrigerant charge while boosting thermal efficiency in heat pumps. Danfoss page: weak ("This design supports improved part-load efficiency and may enable a lower refrigerant charge in certain systems.").

### G3. Double-wall technology pitch and performance

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Suggestion for generate_variants.py:** Give double-wall technology its own dedicated section explaining that two plates per flow channel are used so liquids can never mix and internal leaks become visible from the outside.
- **Wiki already has** (wiki/technologies/double-wall-option.md):
  - "Two plates per flow channel instead of one."
  - "The liquids can never mix, and any internal leak becomes visible from the outside."
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): the competitor page highlights a new generation of double-wall brazed heat exchangers using a three-barrier technique designed to prevent media mixing with minimal efficiency loss and maximum thermal performance. Danfoss page: weak ("A double wall option uses two plates per flow channel to prevent liquid mixing, making it suitable for applications where contamination must be avoided, such as heat pumps, boilers, and transformer oil cooling.").

### G4. Explicit mention of R290 refrigerant

- **Questions lost:** Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?
- **Suggestion for generate_variants.py:** Explicitly highlight R290 alongside R32 under supported refrigerants for heat pump models.
- **Wiki already has** (wiki/platforms/heat-pump-platforms.md, wiki/technologies/z-design-series.md):
  - "Supported refrigerants for heat pump models: R32, R290, R410A, R454B, R454C, R455A"
  - "Optimised for multiple low-GWP refrigerants."
- **Evidence:**
  - plain_1 lost to Alfa Laval (alfa_laval_1): The competitor page explicitly names propane (R290) and identifies the CB24 model as optimized for it. Danfoss page: missing.
  - plain_1 lost to Alfa Laval (alfa_laval_1): The competitor page highlights a specific model (CB24) engineered as a compact condenser fully optimized for propane (R290) to minimize refrigerant charge. Danfoss page: weak ("The Z-design is optimized for multiple low-GWP refrigerants, aligning with modern sustainability goals.").

### G5. Specific compact condenser model lines

- **Questions lost:** What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?
- **Suggestion for generate_variants.py:** Highlight specific condenser model designations suitable for 10 kW heat pump applications, such as the H30(L)-C under Platform 30.
- **Wiki already has** (wiki/platforms/heat-pump-platforms.md):
  - "| 30 | 95 x 320 | 3-10 | condensers H30(L)-C, H30-CW, HDW30-C (double wall) |"
- **Evidence:**
  - plain_3 lost to Alfa Laval (alfa_laval_1): the competitor page highlights specific model designations such as the CB24, explicitly calling it a compact condenser fully optimized for heat pumps. Danfoss page: missing.

### G6. Application focus on domestic hot water

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Suggestion for generate_variants.py:** Prominently feature domestic hot water systems as a primary application alongside heat pumps, chillers, and district energy.
- **Wiki already has** (wiki/products/micro-plate-bphe-heat-pumps.md):
  - "Heat pumps, chillers, district energy and domestic hot water systems."
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): the competitor page features domestic hot water as a primary application across multiple sections, including general duties and residential heating. Danfoss page: weak ("These heat exchangers are ideal for heat pumps, chillers, district energy systems, and domestic hot water applications.").

### G7. Explicit evaporator application positioning

- **Questions lost:** What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Suggestion for generate_variants.py:** Explicitly position Danfoss brazed plate heat exchangers for heating, cooling, and refrigeration applications, and highlight dedicated evaporator models such as H118(L)-E.
- **Wiki already has** (wiki/company/danfoss.md, wiki/platforms/heat-pump-platforms.md):
  - "What the company does, in one sentence: Danfoss offers a complete portfolio of brazed plate heat exchangers (BPHE) for heating, cooling and refrigeration."
  - "| 118 | 186 x 613 | 30-130 | evaporators H118(L)-E, H118L-EZ; condensers H118(L)-C, H118L-CZ |"
- **Evidence:**
  - plain_2 lost to SWEP (swep_1): the competitor page explicitly states its heat exchangers are ideal for use as evaporators, condensers, or economizers in HVAC or refrigeration. Danfoss page: weak ("The Micro Plate™ exchangers are suitable for heat pumps, chillers, district energy systems, and domestic hot water applications.").

## 4. Wiki gaps

The wiki has nothing (or not enough) on this, so no generator can write it. Each one is a proposal in WIKI_PROPOSALS.md marked **NEEDS DANFOSS SOURCE**.

### P1. Specific model dedicated to charge reduction  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Which heat exchanger helps reduce the refrigerant charge of a heat pump?; Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?
- **Missing:** Does the eBrochure specify a heat exchanger model designed specifically to minimize refrigerant charge in heat pumps?
- **Belongs in:** `wiki/platforms/heat-pump-platforms.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page highlights a specific model, the CB24 compact condenser, engineered specifically to minimize refrigerant charge in heat pumps and commercial refrigeration.
  - plain_1 lost to Alfa Laval (alfa_laval_1): The competitor page highlights a specific model (CB24) engineered as a compact condenser fully optimized for propane (R290) to minimize refrigerant charge.

### P2. Selection software features and capabilities  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Which brazed plate heat exchanger suppliers offer selection software?; What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Missing:** Does the brochure detail specific features of HEXSelector software, such as calculation modes, web accessibility, multi-language support, or calculation saving and sharing capabilities?
- **Belongs in:** `wiki/services/hexselector.md` (existing)
- **Source to check:** eBrochure AD565353287087en-000101 (or another Danfoss software user manual if not in the eBrochure).
- **Evidence:**
  - stats_1 lost to SWEP (swep_1): The competitor page details two dedicated dimensioning software tools (SWEP SSP and DThermX), highlighting features such as three calculation modes (design, performance, rating), online access with no download needed, fast calculations that can be saved and shared, and multi-language support.
  - plain_2 lost to SWEP (swep_1): the competitor page details two separate dimensioning tools (SWEP SSP and DThermX) featuring three calculation modes and replacement cross-reference tools

### P3. Replacement product cross-reference tools  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Which brazed plate heat exchanger suppliers offer selection software?
- **Missing:** Does Danfoss provide an online cross-reference tool or database for finding replacement heat exchanger products?
- **Belongs in:** `wiki/services/cross-reference-tool.md` (new file)
- **Source to check:** Another Danfoss document would be needed, as eBrochure AD565353287087en-000101 does not mention replacement cross-reference tools.
- **Evidence:**
  - stats_1 lost to SWEP (swep_1): The competitor page mentions integrated online tools for finding replacement products (SWEP cross reference and Xreference).

### P4. Third-party certification and industry approvals  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Missing:** Does the eBrochure or another Danfoss document state whether Danfoss brazed plate heat exchangers have AHRI certification or major pressure vessel and marine industry approvals?
- **Belongs in:** `wiki/company/certifications.md` (new file)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101 or another Danfoss document
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): the competitor page states that CB heat exchangers are available with AHRI certification for liquid-to-liquid heat exchangers and major pressure vessel and marine industry approvals

### P5. Explicit operating pressure specifications  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?
- **Missing:** Does the eBrochure specify concrete operating pressure ratings and pressure fatigue resistance for heat pump brazed plate heat exchangers?
- **Belongs in:** `wiki/products/micro-plate-bphe-heat-pumps.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101 (or another Danfoss technical document if not present in the eBrochure)
- **Evidence:**
  - plain_3 lost to Alfa Laval (alfa_laval_1): the competitor page gives concrete operating pressure ratings ranging from 32 to 90 bar and highlights pressure fatigue resistance

### P6. High-capacity output range  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Missing:** Does Danfoss offer heat exchanger models designed for high-capacity applications reaching into the megawatt range?
- **Belongs in:** `wiki/platforms/heat-pump-platforms.md` (existing)
- **Source to check:** A broader Danfoss heat exchanger catalog or product documentation beyond eBrochure AD565353287087en-000101.
- **Evidence:**
  - plain_2 lost to SWEP (swep_1): the competitor page highlights high-capacity models capable of handling duties up to several megawatts of heating or cooling

## Appendix: reviewer output per question

### Which heat exchanger helps reduce the refrigerant charge of a heat pump?

Danfoss page `stats_1` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Brazed plate heat exchangers from Alfa Laval and Danfoss are specifically designed to help reduce the refrigerant charge in a heat pump:
> * **Alfa Laval CB24**: This compact brazed plate heat exchanger uses a patented asymmetrical channel plate design engineered specifically to minimize refrigerant charge while boosting thermal efficiency, making it ideal for ground source heat pumps and commercial refrigeration [Alfa Laval (alfa_laval_1)].
> * **Danfoss Micro Plate™ Heat Exchangers**: Featuring a patented dimple pattern and an asymmetric Z-shaped flow design, these exchangers mix fluid phases efficiently to achieve high heat transfer with fewer plates, enabling lower refrigerant charges in variable-load heat pump systems [Danfoss (stats_1)].
> Both manufacturers provide effective solutions for minimizing refrigerant usage while maintaining high thermal performance [Alfa Laval (alfa_laval_1); Danfoss (stats_1)].
> RECOMMENDED: Alfa Laval

1. **Specific model dedicated to charge reduction** (weak on the Danfoss page): The competitor page highlights a specific model, the CB24 compact condenser, engineered specifically to minimize refrigerant charge in heat pumps and commercial refrigeration. *Why:* The AI answer cited the Alfa Laval CB24 by name as the specific product example designed to reduce refrigerant charge in heat pumps.
2. **Prominent section focus on charge reduction** (weak on the Danfoss page): The competitor page features a dedicated section header titled 'Reduce your charge. Increase your potential.' explicitly positioning charge reduction as a primary capability. *Why:* The clear heading on the competitor page makes refrigerant charge reduction stand out as a core benefit rather than a brief concluding clause.

### Which brazed plate heat exchanger suppliers offer selection software?

Danfoss page `stats_1` vs `SWEP / swep_1`, AI recommended: **SWEP**

AI answer:

> Based on the provided search results, two suppliers offer selection and dimensioning software for their brazed plate heat exchangers:
> * **SWEP**: Provides selection and dimensioning tools, including the SWEP SSP and DThermX software [SWEP (swep_1)]. These online programs allow users to input specific design parameters to calculate the optimal heat exchanger design across modes for design, performance, and rating [SWEP (swep_1)].
> * **Danfoss**: Offers the HEXSelector software to aid users in choosing the appropriate brazed plate heat exchanger for their application [Danfoss (stats_1)].
> Other suppliers mentioned in the search results, such as Hexonic [Hexonic (hexonic_3); Hexonic (hexonic_2)] and Alfa Laval [Alfa Laval (alfa_laval_1)], do not explicitly mention offering selection software.
> RECOMMENDED: SWEP

1. **Selection software features and capabilities** (weak on the Danfoss page): The competitor page details two dedicated dimensioning software tools (SWEP SSP and DThermX), highlighting features such as three calculation modes (design, performance, rating), online access with no download needed, fast calculations that can be saved and shared, and multi-language support. *Why:* The AI explicitly listed SWEP's named tools and their calculation modes (design, performance, rating) in the answer, making SWEP the primary recommendation due to richer software feature details.
2. **Replacement product cross-reference tools** (missing on the Danfoss page): The competitor page mentions integrated online tools for finding replacement products (SWEP cross reference and Xreference). *Why:* The competitor page provides additional selection tool functionality for replacement units, which the Danfoss page does not mention.

### Who makes double-wall brazed plate heat exchangers for domestic hot water?

Danfoss page `stats_1` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Based on the search results, three major manufacturers produce double-wall brazed plate heat exchangers suitable for domestic hot water applications:
> * **Danfoss:** Offers double-wall options in its Micro Plate™ brazed plate heat exchanger line (such as the HDW30-C and HDW44-C models) [Danfoss (stats_1)]. These use two plates per flow channel to prevent liquid contamination, making them ideal for domestic hot water systems [Danfoss (stats_1)].
> * **Alfa Laval:** Manufactures double-wall brazed plate heat exchangers (including models in its CB line) engineered with a three-barrier technique to prevent media mixing while maintaining thermal performance for domestic hot water and residential heating [Alfa Laval (alfa_laval_1)].
> * **Hexonic:** Produces the SafePLATE series, which features a double-wall system designed to safeguard fluids in domestic hot water and heating installations [Hexonic (hexonic_2)].
> RECOMMENDED: Alfa Laval

1. **Double-wall technology pitch and performance** (weak on the Danfoss page): the competitor page highlights a new generation of double-wall brazed heat exchangers using a three-barrier technique designed to prevent media mixing with minimal efficiency loss and maximum thermal performance *Why:* The AI specifically cited Alfa Laval's three-barrier technique and protection against media mixing while maintaining thermal performance, directly reflecting the competitor's main double-wall feature.
2. **Application focus on domestic hot water** (weak on the Danfoss page): the competitor page features domestic hot water as a primary application across multiple sections, including general duties and residential heating *Why:* The Danfoss page is titled and structured around heat pumps rather than domestic hot water, making the competitor appear more specialized for the buyer's target application.
3. **Third-party certification and industry approvals** (missing on the Danfoss page): the competitor page states that CB heat exchangers are available with AHRI certification for liquid-to-liquid heat exchangers and major pressure vessel and marine industry approvals *Why:* Independent performance verification and certifications like AHRI give buyers extra trust when choosing a manufacturer for domestic hot water systems.

### Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?

Danfoss page `plain_1` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Several brazed plate heat exchangers are engineered to work with low-GWP and modern refrigerants:
> * **Alfa Laval CB Series**: The CB line, specifically the CB24 model, is designed for efficient performance with any refrigerant type and is fully optimized for propane (R290), reducing refrigerant charge while maximizing thermal efficiency [Alfa Laval (alfa_laval_1)].
> * **Danfoss Micro Plate™ Series**: Danfoss Z-design micro plate heat exchangers utilize an asymmetric flow configuration optimized for multiple low-GWP refrigerants to support sustainability objectives [Danfoss (plain_1)].
> * **Hexonic R Series**: Built with a specialized corrugation geometry and a Refrigerant Distribution System (RDS), the R series is optimized for modern refrigerants in heat pump and refrigeration applications [Hexonic (hexonic_3)].
> RECOMMENDED: Alfa Laval

1. **Explicit mention of R290 refrigerant** (missing on the Danfoss page): The competitor page explicitly names propane (R290) and identifies the CB24 model as optimized for it. *Why:* The prompt specifically asked for heat exchangers working with R290. The AI cited the competitor's explicit R290 compatibility and recommended it over Danfoss.
2. **Specific model for low-GWP application** (weak on the Danfoss page): The competitor page highlights a specific model (CB24) engineered as a compact condenser fully optimized for propane (R290) to minimize refrigerant charge. *Why:* The AI answer specifically cited the CB24 model's R290 optimization in its bullet points, whereas Danfoss was described only by its general product series.

### What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?

Danfoss page `plain_3` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> For a heat pump condenser, several specialized brazed plate heat exchanger options are available based on your exact setup:
> * **Alfa Laval CB Series:** Alfa Laval’s CB line (such as the compact CB24) features an asymmetric plate design optimized for heat pump condenser duties, delivering high thermal efficiency, low refrigerant charge, and resistance to pressure fatigue [Alfa Laval (alfa_laval_1)].
> * **Hexonic R Series:** Engineered specifically for refrigerant-side duty in heat pumps, the R series features specially adjusted corrugation geometry to maximize condensation efficiency and supports working pressures up to 45 bar [Hexonic (hexonic_3)].
> * **Danfoss Micro Plate Series:** Designed for variable-load heat pump applications using micro-plate dimple patterns, with exact sizing determined via Danfoss's HEXSelector software [Danfoss (plain_3)].
> For a compact heat pump condenser application, the **Alfa Laval CB series** is a leading choice [Alfa Laval (alfa_laval_1)].
> RECOMMENDED: Alfa Laval

1. **Specific compact condenser model lines** (missing on the Danfoss page): the competitor page highlights specific model designations such as the CB24, explicitly calling it a compact condenser fully optimized for heat pumps *Why:* The AI recommended the Alfa Laval CB series directly, citing the compact CB24 model as a leading choice for heat pump condenser duty.
2. **Refrigerant charge minimization** (weak on the Danfoss page): the competitor page states that its asymmetric channel plate engineering is built to minimize refrigerant charge while boosting thermal efficiency in heat pumps *Why:* The AI answer specifically cited low refrigerant charge as a key advantage of the winning competitor's asymmetric design for condenser duty.
3. **Explicit operating pressure specifications** (weak on the Danfoss page): the competitor page gives concrete operating pressure ratings ranging from 32 to 90 bar and highlights pressure fatigue resistance *Why:* The AI answer highlighted pressure rating capabilities (e.g. 45 bar for Hexonic, high pressure fatigue resistance for Alfa Laval) as key criteria for heat pump condensers.

### What is the best evaporator heat exchanger for a 100 kW commercial heat pump?

Danfoss page `plain_2` vs `SWEP / swep_1`, AI recommended: **SWEP**

AI answer:

> Brazed plate heat exchangers (BPHEs) are ideal for commercial heat pump evaporators because they deliver high thermal efficiency within a compact footprint [SWEP (swep_1); Alfa Laval (alfa_laval_1)]. 
> Top options for commercial heat pump systems include:
> * **SWEP BPHEs:** Capable of handling heating and cooling duties up to several megawatts, offering customizable plate configurations [SWEP (swep_1)]. Exact sizing can be determined using SWEP SSP™ or DThermX dimensioning software [SWEP (swep_1)].
> * **Danfoss Micro Plate™:** Tailored for medium to large commercial heat pumps, using dimple plate technology and distribution chambers to maintain efficiency during part-load conditions [Danfoss (plain_2)].
> * **Hexonic R Series:** Uses a Refrigerant Distribution System (RDS) to ensure even evaporation across the plate surface [Hexonic (hexonic_3)].
> * **Alfa Laval CB Series:** Features high-capacity models like the CB210 for demanding HVAC applications [Alfa Laval (alfa_laval_1)].
> To select the precise heat exchanger for a 100 kW system, input your operational parameters into selection tools like SWEP SSP or Danfoss HEXSelector [SWEP (swep_1); Danfoss (plain_2)].
> RECOMMENDED: SWEP

1. **Explicit evaporator application positioning** (weak on the Danfoss page): the competitor page explicitly states its heat exchangers are ideal for use as evaporators, condensers, or economizers in HVAC or refrigeration *Why:* The user query specifically asks for an evaporator heat exchanger, and the competitor page explicitly highlights evaporator duties in its core application description.
2. **High-capacity output range** (weak on the Danfoss page): the competitor page highlights high-capacity models capable of handling duties up to several megawatts of heating or cooling *Why:* The buyer specifies a 100 kW commercial heat pump size, and the AI explicitly cited SWEP's capability to handle heating and cooling duties up to several megawatts.
3. **Dimensioning software options** (weak on the Danfoss page): the competitor page details two separate dimensioning tools (SWEP SSP and DThermX) featuring three calculation modes and replacement cross-reference tools *Why:* The AI directs the user to input parameters into selection tools to size a 100 kW system, explicitly naming both SWEP SSP and DThermX software.

