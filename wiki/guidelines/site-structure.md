---
type: Guideline
title: Site structure
description: How pages are organised and linked so that Google finds every page, understands the catalog and passes authority from the strong pages to the product pages.
tags: [guideline, site structure, internal links, authority, googlebot]
applies_to: app
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T22:45:00Z
---
# Why
Google discovers pages by following links, and links pass signals (authority) from one page to another. A catalog page that many pages link to, and that links to its product pages, spreads that authority to them. A page that no page links to (an orphan), or that sits many clicks deep, is found late and counts for little. Inside a site this is the part we control. Authority from outside (other sites, distributors, trade press linking to Danfoss) adds to it, but comes from earned media, not from the page itself.

# Rules
- One hub page per product family (for example "Heat exchangers"), linking to every category page with a tile: a descriptive title and one or two sentences.
- Each category page links back to the hub and to its product pages. Product pages link back to their category and to closely related products.
- Every page is at most 3 clicks from the hub. No orphan pages.
- Link text says what the target page is about ("Brazed plate heat exchangers for heat pumps"), not "Read more" alone.
- Breadcrumbs on every page, also as BreadcrumbList structured data with working, absolute links.
- One main topic per page, with its own address. Do not split one topic over several thin pages, and do not answer the same question on several pages.
- All the text and links are in the HTML of the first response. Catalog tiles, product ranges and document lists must not need JavaScript to appear.
- Every page is in the sitemap (see [Sitemap](sitemap.md)).

# How the app applies this
The Web page tab copies a section of danfoss.com (for example the heat exchanger catalog) as a small website and checks it:
- pages a crawler cannot reach from the first page;
- orphan pages;
- pages more than 3 clicks deep;
- pages missing from the sitemap;
- Danfoss pages whose text needs JavaScript.

Each page's list entry shows how many pages link to it and how many it links to.
