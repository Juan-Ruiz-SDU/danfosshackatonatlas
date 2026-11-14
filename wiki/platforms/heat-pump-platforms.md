---
type: Product Range
title: Heat pump platforms
description: The 11 Danfoss heat pump platforms from the eBrochure heat pump table, with outline, capacity and models, covering 2 kW to 300 kW.
tags: [platforms, models, capacity, dimensions, refrigerants]
sources:
  - id: ebrochure
    resource: /references/danfoss-bphe-ebrochure.md
    title: 'Danfoss eBrochure "Danfoss brazed plate heat exchangers", AD565353287087en-000101 (06-2026), heat pump table'
  - id: r290-news
    resource: https://www.danfoss.com/en/about-danfoss/news/dcs/optimized-and-ultra-safe-brazed-plate-heat-exchangers-for-r290-from-danfoss-lower-refrigerant-charge-and-higher-heat-transfer/
    title: 'danfoss.com news "Optimized R290 brazed plate heat exchangers: Lower charge and higher heat transfer" (2024-09-30)'
  - id: hdw44c-datasheet
    resource: https://assets.danfoss.com/documents/latest/205036/AI356147463903en-000101.pdf
    title: 'Danfoss data sheet "Micro plate heat exchanger, type HDW44-C", AI356147463903en-000101 (2022.07)'
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T12:57:12Z
---
# Summary
- Number of heat pump platforms: 11 (platforms 17, 22, 30, 34, 39, 44, 48, 55, 62, 118, 129-D)[^ebrochure]
- Overall heat pump capacity range: 2 kW to 300 kW[^ebrochure]
- Supported refrigerants for heat pump models: R32, R290, R410A, R454B, R454C, R455A[^ebrochure]

# Platforms
All figures from the eBrochure heat pump table.[^ebrochure]

| Platform | Outline (mm) | Capacity (kW) | Models |
|---|---|---|---|
| 17 | 95 x 178 | 2-15 | H17L-CZ condenser, H17L-CZ SGHX |
| 22 | 76 x 312 | 2-20 | H22(L)-E evaporator, H22(L)-C condenser |
| 30 | 95 x 320 | 3-10 | condensers H30(L)-C, H30-CW, HDW30-C (double wall) |
| 34 | 118 x 289 | 2-20 | SGHX H34L-CL, H34L-CM |
| 39 | 117 x 331 | 5-15 | evaporator H39L-EZU |
| 44 | 119 x 376 | 2-15 | condenser HDW44-C (double wall) |
| 48 | 126 x 386 | 10-150 | condensers and SGHX H48T-CH, H48T-CL |
| 55 | 109 x 525 | 5-40 | condenser H55(L)-C |
| 62 | 118 x 525 | 5-50 | evaporators H62(L)-E, H62(L)-EZU; condensers H62(L)-C, H62(L)-CX, H62L-CZ |
| 118 | 186 x 613 | 30-130 | evaporators H118(L)-E, H118L-EZ; condensers H118(L)-C, H118L-CZ |
| 129-D | 246 x 525 | 50-300 | evaporator H129L-EZD, condenser H129L-CZD |

# Max. working pressure (per model, from Danfoss data)
| Model | Platform | Refrigerant side | Water side |
|---|---|---|---|
| H39L-EZU | 39 | 49 bar (711 psi) | 25 bar (363 psi)[^r290-news] |
| H62L-CZ | 62 | 49 bar (711 psi) | 25 bar (363 psi)[^r290-news] |
| HDW30-C | 30 | 35 bar (508 psi) | 16 bar (232 psi)[^r290-news] |
| HDW44-C | 44 | 35 bar (508 psi) | 16 bar (232 psi)[^hdw44c-datasheet][^r290-news] |

Other models: no pressure data in our sources.

Double wall models are described in [Double wall option](/technologies/double-wall-option.md).

[^ebrochure]: Danfoss eBrochure "Danfoss brazed plate heat exchangers", document AD565353287087en-000101, (c) Danfoss 06-2026, heat pump table.
[^r290-news]: danfoss.com news "Optimized R290 brazed plate heat exchangers: Lower charge and higher heat transfer", https://www.danfoss.com/en/about-danfoss/news/dcs/optimized-and-ultra-safe-brazed-plate-heat-exchangers-for-r290-from-danfoss-lower-refrigerant-charge-and-higher-heat-transfer/, published 2024-09-30, section "Product range".
[^hdw44c-datasheet]: Danfoss data sheet "Micro plate heat exchanger, type HDW44-C", document AI356147463903en-000101, (c) Danfoss 2022.07, page 2, https://assets.danfoss.com/documents/latest/205036/AI356147463903en-000101.pdf.
