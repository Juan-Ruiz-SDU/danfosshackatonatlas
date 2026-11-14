# Citation lab review (2026-11-14_175811)

- Run `lab/results/2026-11-14_173647_gemini`: normal, `gemini/gemini-3.6-flash`, 144 trials
- Run `lab/results/2026-11-14_175212_gemini`: --force-target, `gemini/gemini-3.6-flash`, 144 trials
- Reviewer: `gemini/gemini-3.6-flash`
- Content losses taken from: the --force-target run (page always shown)

## Summary

- **Wording losses** (Danfoss page not in BM25's top 5): 1 questions
- **Content losses** (shown, but a competitor was preferred): 8 questions, 7 where a rewritten variant lost
- **Generator problems** (the wiki has it, the variants leave it out): 5
- **Wiki gaps** (proposals in WIKI_PROPOSALS.md, all NEEDS DANFOSS SOURCE): 10

## 1. Wording losses

The page never reached the AI. Fix by using the buyer's words (only where the wiki supports the topic). Ranked by share of trials lost.

| # | Question | Lost | Pages not found (rank) | Buyer words missing from the page |
|---|---|---|---|---|
| W1 | Who makes double-wall brazed plate heat exchangers for domestic hot water? | 4/12 | original_1 (#6), stats_1 (#6) | double-wall (2), domestic, hot |

### W1. Who makes double-wall brazed plate heat exchangers for domestic hot water?

- **original_1** (original): rank 6, BM25 score 0.65 vs 1.88 for the last page shown (SWEP (swep_1)).
  - missing `double-wall`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2)
  - missing `domestic`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2), Hexonic (hexonic_1)
  - missing `hot`: used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2), Hexonic (hexonic_1), SWEP (swep_2), SWEP (swep_1)
  - question phrasing only, not worth adding: `make`
- **stats_1** (stats): rank 6, BM25 score 1.49 vs 1.7 for the last page shown (SWEP (swep_1)).
  - missing `double-wall` (the page only has `double`, `wall`: the lab's BM25 does not match word forms): used by Alfa Laval (alfa_laval_1), Hexonic (hexonic_2)
  - question phrasing only, not worth adding: `make`

## 2. Content losses

The AI saw the Danfoss page and still preferred a competitor. Ranked by loss rate.

| # | Question | Lost | Winner (times) | Losses by style | Reviewed |
|---|---|---|---|---|---|
| C1 | Which heat exchanger helps reduce the refrigerant charge of a heat pump? | 11/12 | Alfa Laval / alfa_laval_1 (11) | original 2/2, plain 5/6, stats 4/4 | stats_2 vs alfa_laval_1 |
| C2 | Which brazed plate heat exchanger suppliers offer selection software? | 10/12 | SWEP / swep_1 (10) | original 2/2, plain 4/6, stats 4/4 | stats_2 vs swep_1 |
| C3 | What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump? | 8/12 | Hexonic / hexonic_3 (8) | original 2/2, plain 6/6, stats 0/4 | plain_3 vs hexonic_3 |
| C4 | Who makes double-wall brazed plate heat exchangers for domestic hot water? | 7/12 | Alfa Laval / alfa_laval_1 (6), Hexonic / hexonic_2 (1) | original 2/2, plain 3/6, stats 2/4 | stats_1 vs alfa_laval_1 |
| C5 | Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32? | 5/12 | Alfa Laval / alfa_laval_1 (5) | original 2/2, plain 3/6, stats 0/4 | plain_1 vs alfa_laval_1 |
| C6 | What is the best evaporator heat exchanger for a 100 kW commercial heat pump? | 3/12 | SWEP / swep_1 (2), Hexonic / hexonic_3 (1) | original 0/2, plain 3/6, stats 0/4 | plain_3 vs swep_1 |
| C7 | Copper-brazed or nickel-brazed plate heat exchanger: which supplier should I choose? | 2/12 | Hexonic / hexonic_3 (2) | original 2/2, plain 0/6, stats 0/4 | only the public original lost: not reviewed |
| C8 | What is the best brazed plate heat exchanger for heat pumps? | 1/12 | Alfa Laval / alfa_laval_1 (1) | original 0/2, plain 0/6, stats 1/4 | stats_2 vs alfa_laval_1 |

## 3. Generator problems

The wiki already has this information; the variants leave it out or bury it. Fix in `generate_variants.py` (prompt or styles). Ranked by importance.

### G1. Explicit mention of reducing refrigerant charge

- **Questions lost:** Which heat exchanger helps reduce the refrigerant charge of a heat pump?; Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?; What is the best brazed plate heat exchanger for heat pumps?
- **Suggestion for generate_variants.py:** Highlight under a dedicated heading or section how Micro Plate™ technology enables a lower refrigerant charge in many heat pump systems.
- **Wiki already has** (wiki/platforms/heat-pump-platforms.md, wiki/technologies/micro-plate-pattern.md):
  - "In many systems it also enables a lower refrigerant charge."
  - "Supported refrigerants for heat pump models: R32, R290, R410A, R454B, R454C, R455A"
- **Evidence:**
  - stats_2 lost to Alfa Laval (alfa_laval_1): The competitor page explicitly states under a dedicated heading ('Reduce your charge') that the Alfa Laval CB24 minimizes the refrigerant charge in heat pumps. Danfoss page: missing.
  - plain_1 lost to Alfa Laval (alfa_laval_1): The competitor page explicitly states that the Alfa Laval CB24 model is 'fully optimized for propane (R290)'. Danfoss page: weak ("The Z-design is optimized for multiple low-GWP refrigerants, aligning with modern sustainability goals.").
  - stats_2 lost to Alfa Laval (alfa_laval_1): the competitor page highlights the CB24 model as optimized for propane (R290) to minimize refrigerant charge while boosting efficiency. Danfoss page: weak ("Compatibility**: Supports refrigerants including R32, R290, R410A, R454B, R454C, and R455A.").

### G2. Double-wall design technology details

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Suggestion for generate_variants.py:** Highlight the double-wall construction of using two plates per flow channel so liquids can never mix and internal leaks become visible.
- **Wiki already has** (wiki/technologies/double-wall-option.md):
  - "Two plates per flow channel instead of one."
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page states that its double-wall brazed heat exchangers use a three-barrier technique to provide maximum protection against media mixing with limited loss to efficiency. Danfoss page: weak ("A double wall option uses two plates per flow channel to prevent liquid mixing, making it suitable for applications where contamination must be avoided").

### G3. Dedicated condenser phase-change design

- **Questions lost:** What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?
- **Suggestion for generate_variants.py:** Highlight dedicated Danfoss heat pump condenser models (such as platform 30 H30(L)-C for 3-10 kW capacities) under a clear heading and explain how the Micro Plate dimple corrugation pattern and Z-design series flow keep liquid and vapour phases well mixed during condenser duty.
- **Wiki already has** (wiki/platforms/heat-pump-platforms.md, wiki/products/micro-plate-bphe-heat-pumps.md):
  - "An asymmetric Z-shaped flow that keeps liquid and vapour phases well mixed."
  - "A patented plate design with a dimple pattern instead of the classic [Fishbone](/technologies/fishbone-pattern.md) (herringbone) corrugation."
  - "| 30 | 95 x 320 | 3-10 | condensers H30(L)-C, H30-CW, HDW30-C (double wall) |"
- **Evidence:**
  - plain_3 lost to Hexonic (hexonic_3): The competitor page states the R series features specially adjusted corrugation geometry engineered specifically for efficient phase-change heat transfer in condenser duty. Danfoss page: weak ("Danfoss Micro Plate™ heat exchangers are used in heat pumps, chillers, district energy systems, and domestic hot water applications.").

### G4. Primary application framing and focus

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Suggestion for generate_variants.py:** Feature domestic hot water prominently in the introductory text and high-level application summaries.
- **Wiki already has** (wiki/products/micro-plate-bphe-heat-pumps.md):
  - "Heat pumps, chillers, district energy and domestic hot water systems."
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page highlights domestic hot water prominently in the introductory text and includes a dedicated section for residential heating and domestic hot water applications. Danfoss page: weak ("Danfoss Micro Plate™ Brazed Plate Heat Exchangers for Heat Pumps").

### G5. Specific product model for low-GWP duty

- **Questions lost:** Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?
- **Suggestion for generate_variants.py:** Include specific heat pump condenser model designations such as H17L-CZ condenser when referencing models compatible with low-GWP refrigerants like R290.
- **Wiki already has** (wiki/platforms/heat-pump-platforms.md):
  - "| 17 | 95 x 178 | 2-15 | H17L-CZ condenser, H17L-CZ SGHX |"
- **Evidence:**
  - plain_1 lost to Alfa Laval (alfa_laval_1): The competitor page identifies a specific model, the 'Alfa Laval CB24', as a compact condenser optimized for propane (R290). Danfoss page: missing.

## 4. Wiki gaps

The wiki has nothing (or not enough) on this, so no generator can write it. Each one is a proposal in WIKI_PROPOSALS.md marked **NEEDS DANFOSS SOURCE**.

### P1. Selection software features and capabilities  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Which brazed plate heat exchanger suppliers offer selection software?
- **Missing:** Does Danfoss documentation specify the features and capabilities of HEXSelector, such as calculation modes, online availability, calculation saving or sharing, language support, or replacement cross-reference tools?
- **Belongs in:** `wiki/services/hexselector.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101; another Danfoss document would be needed if not present in the brochure.
- **Evidence:**
  - stats_2 lost to SWEP (swep_1): the competitor page details two specific dimensioning software tools (SWEP SSP™ and DThermX) and lists key features such as three calculation modes (design, performance, rating), full online availability without downloads, calculation saving/sharing, multi-language support, and integrated replacement cross-reference tools

### P2. Operating pressure specifications  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?
- **Missing:** Does the eBrochure specify the maximum operating pressure rating (in bar) for Danfoss brazed plate heat exchangers?
- **Belongs in:** `wiki/products/micro-plate-bphe-heat-pumps.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101; another Danfoss technical specification document would be needed if not in the eBrochure.
- **Evidence:**
  - plain_3 lost to Hexonic (hexonic_3): The competitor page specifies a high operating pressure capability of up to 45 bar for cooling medium pressures.

### P3. Multiple distinct software offerings  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Which brazed plate heat exchanger suppliers offer selection software?
- **Missing:** Does Danfoss offer multiple distinct selection software tools for BPHE selection in addition to HEXSelector?
- **Belongs in:** `wiki/services/hexselector.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101; another Danfoss document would be needed if not present in the brochure.
- **Evidence:**
  - stats_2 lost to SWEP (swep_1): the competitor page explicitly introduces two distinct selection software tools (SWEP SSP™ and DThermX) designed for optimal BPHE selection

### P4. Double-wall design technology details  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Missing:** Does the brochure specify whether Danfoss double-wall heat exchangers use a three-barrier technique or describe the impact of double-wall construction on heat exchanger efficiency?
- **Belongs in:** `wiki/technologies/double-wall-option.md` (existing)
- **Source to check:** eBrochure AD565353287087en-000101 or another Danfoss technical document
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page states that its double-wall brazed heat exchangers use a three-barrier technique to provide maximum protection against media mixing with limited loss to efficiency.

### P5. Primary application framing and focus  (NEEDS DANFOSS SOURCE)

- **Questions lost:** Who makes double-wall brazed plate heat exchangers for domestic hot water?
- **Missing:** Does Danfoss documentation provide dedicated application guidance or detailed framing specifically for residential heating and domestic hot water applications?
- **Belongs in:** `wiki/products/micro-plate-bphe-heat-pumps.md` (existing)
- **Source to check:** eBrochure AD565353287087en-000101 or another Danfoss application document
- **Evidence:**
  - stats_1 lost to Alfa Laval (alfa_laval_1): The competitor page highlights domestic hot water prominently in the introductory text and includes a dedicated section for residential heating and domestic hot water applications.

### P6. dimensioning software details  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Missing:** Does the brochure describe specific calculation modes or input parameters available in HEXSelector software?
- **Belongs in:** `wiki/services/hexselector.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101 (a dedicated HEXSelector document would be needed if not present in the eBrochure)
- **Evidence:**
  - plain_3 lost to SWEP (swep_1): the competitor page provides detailed sections on its SSP and DThermX dimensioning software, noting three calculation modes (design, performance, rating) for inputting precise design parameters online

### P7. explicit megawatt capacity range  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best evaporator heat exchanger for a 100 kW commercial heat pump?
- **Missing:** Does the brochure list heat exchanger models or portfolios with megawatt-scale capacity?
- **Belongs in:** `wiki/platforms/heat-pump-platforms.md` (existing)
- **Source to check:** Danfoss eBrochure AD565353287087en-000101 (another Danfoss product brochure would be needed if megawatt-scale units exist in other portfolios)
- **Evidence:**
  - plain_3 lost to SWEP (swep_1): the competitor page explicitly states its portfolio ranges from small units up to high-capacity models capable of handling several megawatts of heating or cooling

### P8. Defrosting and ice formation protection  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best brazed plate heat exchanger for heat pumps?
- **Missing:** Does the eBrochure specify any design features or guidelines for defrosting cycles or preventing ice formation in heat pump duties?
- **Belongs in:** `wiki/technologies/ice-protection.md` (new file)
- **Source to check:** eBrochure AD565353287087en-000101; if not present, another Danfoss technical document would be needed.
- **Evidence:**
  - stats_2 lost to Alfa Laval (alfa_laval_1): the competitor page highlights a patented IceSafe feature designed to prevent crystal formation during defrosting cycles in heat pump condenser duties

### P9. Explicit pressure resistance ratings  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best brazed plate heat exchanger for heat pumps?
- **Missing:** Does the eBrochure list explicit pressure resistance ratings (in bar) for each heat pump BPHE platform?
- **Belongs in:** `wiki/platforms/heat-pump-platforms.md` (existing)
- **Source to check:** eBrochure AD565353287087en-000101; if not present, another Danfoss data sheet would be needed.
- **Evidence:**
  - stats_2 lost to Alfa Laval (alfa_laval_1): the competitor page states high mechanical resistance with explicit pressure ratings ranging from 32 to 90 bar
  - stats_2 lost to Alfa Laval (alfa_laval_1): the competitor page highlights the CB24 model as optimized for propane (R290) to minimize refrigerant charge while boosting efficiency

### P10. Third-party AHRI certification  (NEEDS DANFOSS SOURCE)

- **Questions lost:** What is the best brazed plate heat exchanger for heat pumps?
- **Missing:** Does the eBrochure mention AHRI certification or third-party performance verification for Danfoss BPHE models?
- **Belongs in:** `wiki/products/micro-plate-bphe-heat-pumps.md` (existing)
- **Source to check:** eBrochure AD565353287087en-000101; if not present, another Danfoss document would be needed.
- **Evidence:**
  - stats_2 lost to Alfa Laval (alfa_laval_1): the competitor page notes availability of AHRI certification providing independent third-party performance verification

## Appendix: reviewer output per question

### Which heat exchanger helps reduce the refrigerant charge of a heat pump?

Danfoss page `stats_2` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> The **Alfa Laval CB24** brazed plate heat exchanger helps reduce the refrigerant charge in heat pumps (such as ground source heat pumps) and commercial refrigeration applications [Alfa Laval (alfa_laval_1)]. 
> Featuring advanced engineering with a patented asymmetrical channel plate design (FlexFlow), the CB24 minimizes the required refrigerant charge while boosting thermal efficiency [Alfa Laval (alfa_laval_1)]. It is designed as a compact condenser fully optimized for natural refrigerants like propane (R290), providing a safe, reliable, and sustainable system solution compliant with strict environmental regulations [Alfa Laval (alfa_laval_1)]. Overall, Alfa Laval's CB line offers high thermal performance and high pressure resistance within a compact footprint [Alfa Laval (alfa_laval_1)].
> RECOMMENDED: Alfa Laval

1. **Explicit mention of reducing refrigerant charge** (missing on the Danfoss page): The competitor page explicitly states under a dedicated heading ('Reduce your charge') that the Alfa Laval CB24 minimizes the refrigerant charge in heat pumps. *Why:* The AI directly cited the competitor's CB24 model because the competitor page explicitly addressed reducing/minimizing refrigerant charge in heat pumps.

### Which brazed plate heat exchanger suppliers offer selection software?

Danfoss page `stats_2` vs `SWEP / swep_1`, AI recommended: **SWEP**

AI answer:

> The following brazed plate heat exchanger suppliers offer selection and dimensioning software:
> * **SWEP**: Provides **SWEP SSP™** and **DThermX** dimensioning software to make selecting optimal heat exchangers easy [SWEP (swep_1)]. Users can input design parameters into the software to calculate the best options using design, performance, and rating calculation modes [SWEP (swep_1)]. 
> * **Danfoss**: Offers **Danfoss HEXSelector software**, which aids users in selecting the appropriate unit from their Micro Plate™ brazed plate heat exchanger lineup [Danfoss (stats_2)].
> Other suppliers mentioned, such as Hexonic [Hexonic (hexonic_3); Hexonic (hexonic_2)] and Alfa Laval [Alfa Laval (alfa_laval_1)], do not state in the provided results that they offer selection software.
> RECOMMENDED: SWEP

1. **Selection software features and capabilities** (weak on the Danfoss page): the competitor page details two specific dimensioning software tools (SWEP SSP™ and DThermX) and lists key features such as three calculation modes (design, performance, rating), full online availability without downloads, calculation saving/sharing, multi-language support, and integrated replacement cross-reference tools *Why:* The AI provided a detailed breakdown of SWEP's software features and calculation modes while only giving Danfoss a single sentence mention, leading to SWEP being recommended as the top option.
2. **Multiple distinct software offerings** (weak on the Danfoss page): the competitor page explicitly introduces two distinct selection software tools (SWEP SSP™ and DThermX) designed for optimal BPHE selection *Why:* The AI highlighted both SWEP SSP™ and DThermX by name in the bullet point for SWEP, emphasizing a broader suite of software options.

### What brazed plate heat exchanger should I use as a condenser in a 10 kW heat pump?

Danfoss page `plain_3` vs `Hexonic / hexonic_3`, AI recommended: **Hexonic**

AI answer:

> To select the exact model for a 10 kW heat pump condenser, design parameters can be entered into manufacturer selection tools such as SWEP’s SSP™ or DThermX software [SWEP (swep_1)], or Danfoss’s HEXSelector [Danfoss (plain_3)]. 
> Suitable brazed plate heat exchanger options include:
> - **Hexonic R Series**: Engineered specifically for refrigerant-side condenser duty in heat pumps [Hexonic (hexonic_3)]. It features adjusted corrugation geometry for efficient phase-change heat transfer, handles operating pressures up to 45 bar, and offers copper or stainless LUNA brazing [Hexonic (hexonic_3); Hexonic (hexonic_2)].
> - **Danfoss Micro Plate™**: Uses dimple pattern technology and asymmetric Z-design for improved refrigerant distribution and high efficiency [Danfoss (plain_3)].
> - **SWEP BPHEs**: Provides compact, customizable exchangers designed for residential and commercial heat pump applications [SWEP (swep_1)].
> RECOMMENDED: Hexonic

1. **Operating pressure specifications** (missing on the Danfoss page): The competitor page specifies a high operating pressure capability of up to 45 bar for cooling medium pressures. *Why:* The AI answer explicitly cites the 45 bar operating pressure limit as a key technical feature of the recommended Hexonic model.
2. **Dedicated condenser phase-change design** (weak on the Danfoss page): The competitor page states the R series features specially adjusted corrugation geometry engineered specifically for efficient phase-change heat transfer in condenser duty. *Why:* The AI answer emphasizes Hexonic's specific engineering for refrigerant-side condenser duty, leading to its overall recommendation.

### Who makes double-wall brazed plate heat exchangers for domestic hot water?

Danfoss page `stats_1` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Multiple manufacturers make double-wall brazed plate heat exchangers suitable for domestic hot water applications:
> * **Hexonic:** Manufactures the SafePLATE series, a double-wall copper-brazed plate heat exchanger system designed to protect fluids in indirect domestic hot water applications [Hexonic (hexonic_2)].
> * **Alfa Laval:** Produces double-wall brazed heat exchangers, such as models in its CB line, engineered with a three-barrier technique to prevent media mixing during domestic hot water heating [Alfa Laval (alfa_laval_1)].
> * **Danfoss:** Offers a double-wall option for its Micro Plate™ brazed plate heat exchangers (including HDW double-wall condenser models) that uses two plates per channel to prevent liquid contamination in domestic hot water systems [Danfoss (stats_1)].
> RECOMMENDED: Alfa Laval

1. **Double-wall design technology details** (weak on the Danfoss page): The competitor page states that its double-wall brazed heat exchangers use a three-barrier technique to provide maximum protection against media mixing with limited loss to efficiency. *Why:* The AI cited Alfa Laval's three-barrier technique specifically in its summary and recommended Alfa Laval for double-wall domestic hot water applications.
2. **Primary application framing and focus** (weak on the Danfoss page): The competitor page highlights domestic hot water prominently in the introductory text and includes a dedicated section for residential heating and domestic hot water applications. *Why:* The Danfoss page focuses primarily on heat pumps in its title and main text, mentioning domestic hot water only in the final sentence, whereas the competitor positions domestic hot water as a primary application.

### Which brazed plate heat exchangers work with low-GWP refrigerants like R290 and R32?

Danfoss page `plain_1` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Brazed plate heat exchangers designed to work with low-GWP refrigerants like R290 include:
> * **Alfa Laval CB Series:** Alfa Laval's CB line, specifically the CB24 compact condenser, is fully optimized for propane (R290) [Alfa Laval (alfa_laval_1)]. Its asymmetric FlexFlow plate design enables high thermal efficiency and reduced refrigerant charge across any refrigerant type [Alfa Laval (alfa_laval_1)].
> * **Danfoss Micro Plate™ Series:** The Z-design series of Danfoss Micro Plate™ heat exchangers is optimized for multiple low-GWP refrigerants [Danfoss (plain_1)]. Its dimpled plate pattern and mixing chamber enhance part-load performance and promote even refrigerant distribution [Danfoss (plain_1)].
> * **Hexonic R Series:** Engineered for evaporator and condenser duties in HVAC-R systems, the R series is optimized for modern refrigerants and features a Refrigerant Distribution System (RDS) for even channel distribution [Hexonic (hexonic_3)].
> RECOMMENDED: Alfa Laval

1. **Explicit mention of R290 refrigerant** (weak on the Danfoss page): The competitor page explicitly states that the Alfa Laval CB24 model is 'fully optimized for propane (R290)'. *Why:* The buyer specifically searched for heat exchangers supporting R290 and R32. The competitor page directly names R290, allowing the AI engine to directly validate the match and recommend the competitor, while the Danfoss page only mentions generic low-GWP refrigerants without naming R290 or R32.
2. **Specific product model for low-GWP duty** (missing on the Danfoss page): The competitor page identifies a specific model, the 'Alfa Laval CB24', as a compact condenser optimized for propane (R290). *Why:* The AI answer specifically names the 'CB24 compact condenser' in its summary bullet point and uses it to recommend Alfa Laval over other brands.

### What is the best evaporator heat exchanger for a 100 kW commercial heat pump?

Danfoss page `plain_3` vs `SWEP / swep_1`, AI recommended: **SWEP**

AI answer:

> Brazed plate heat exchangers (BPHEs) are the ideal choice for evaporators in commercial heat pumps, offering high thermal efficiency, compact footprints, and strong pressure resistance [SWEP (swep_1); Alfa Laval (alfa_laval_1); Danfoss (plain_3)]. 
> Key options for commercial duty include:
> - **SWEP**: Provides customizable BPHEs capable of handling heating and cooling capacities from small units up to several megawatts [SWEP (swep_1)]. SWEP offers dedicated SSP and DThermX dimensioning software to calculate and select the exact optimal heat exchanger based on your specific 100 kW parameters [SWEP (swep_1)].
> - **Danfoss**: Features Micro Plate™ BPHEs designed for medium to large commercial heat pumps, utilizing mixing chambers and dimple patterns to enhance part-load efficiency and refrigerant distribution [Danfoss (plain_3)].
> - **Hexonic**: Offers the R series, engineered for heat pump evaporators with a specialized Refrigerant Distribution System (RDS) [Hexonic (hexonic_3)].
> RECOMMENDED: SWEP

1. **dimensioning software details** (weak on the Danfoss page): the competitor page provides detailed sections on its SSP and DThermX dimensioning software, noting three calculation modes (design, performance, rating) for inputting precise design parameters online *Why:* The AI explicitly chose SWEP as the recommended option because its dedicated dimensioning software allows buyers to calculate and select the optimal unit for exact 100 kW parameters.
2. **explicit megawatt capacity range** (missing on the Danfoss page): the competitor page explicitly states its portfolio ranges from small units up to high-capacity models capable of handling several megawatts of heating or cooling *Why:* The AI highlights SWEP's ability to cover capacities up to several megawatts to demonstrate that it comfortably fits commercial 100 kW heat pump duties.

### What is the best brazed plate heat exchanger for heat pumps?

Danfoss page `stats_2` vs `Alfa Laval / alfa_laval_1`, AI recommended: **Alfa Laval**

AI answer:

> Several top manufacturers produce brazed plate heat exchangers (BPHEs) tailored for heat pump evaporators, condensers, and economizers:
> * **Alfa Laval CB Series**: Highly regarded for heat pump applications due to its asymmetric FlexFlow plate design, compact footprint, and patented IceSafe protection against crystal formation during defrosting [Alfa Laval (alfa_laval_1)]. It includes models like the CB24, which is optimized for R290 refrigerant [Alfa Laval (alfa_laval_1)].
> * **Danfoss Micro Plate™**: Tailored for heat pump manufacturers with 11 dedicated platforms, featuring dimpled plate patterns for high turbulence, a mixing chamber, and asymmetric Z-shaped flow to maximize thermal efficiency [Danfoss (stats_2)].
> * **Hexonic R Series**: Features a unique Refrigerant Distribution System (RDS) to ensure even evaporation and reduce steam overheating fluctuations [Hexonic (hexonic_3)].
> * **SWEP**: Offers customizable BPHEs up to 90% smaller than shell-and-tube units [SWEP (swep_1)].
> Alfa Laval's CB line stands out as the premier choice due to its high thermal efficiency, pressure resistance, and specialized refrigerant configurations [Alfa Laval (alfa_laval_1)].
> RECOMMENDED: Alfa Laval

1. **Defrosting and ice formation protection** (missing on the Danfoss page): the competitor page highlights a patented IceSafe feature designed to prevent crystal formation during defrosting cycles in heat pump condenser duties *Why:* The AI specifically cites IceSafe protection against crystal formation during defrosting as a primary feature making the competitor ideal for heat pumps.
2. **Explicit pressure resistance ratings** (missing on the Danfoss page): the competitor page states high mechanical resistance with explicit pressure ratings ranging from 32 to 90 bar *Why:* The AI highlights pressure resistance as one of the main deciding factors when choosing the competitor as the premier heat exchanger for heat pumps.
3. **R290 propane charge optimization** (weak on the Danfoss page): the competitor page highlights the CB24 model as optimized for propane (R290) to minimize refrigerant charge while boosting efficiency *Why:* The AI explicitly points out the competitor's CB24 model being optimized for R290 refrigerant in its recommendation bullet point.
4. **Third-party AHRI certification** (missing on the Danfoss page): the competitor page notes availability of AHRI certification providing independent third-party performance verification *Why:* Third-party validation strengthens the competitor's position as the top choice for performance verification.

