---
type: Guideline
title: Sitemap
description: Every published page is listed in an XML sitemap with its final address and the date it last changed, so Google finds it and reads it again after changes.
tags: [guideline, sitemap, googlebot, crawling, discovery]
applies_to: app
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T20:30:00Z
---
# Why
A sitemap is the list of a site's pages that Google should know about, with the date each one last changed. It helps Google discover new or deeply linked pages (such as one page per product) and decide when to read a page again. It does not raise a page's ranking or its chance of being cited by AI search: it makes sure the page is found and that Google reads the latest version.

# Rules for every page we change or add
- List the page in the site's XML sitemap (sitemaps.org format), with its final address: the canonical URL that answers 200, never an address that redirects.
- Give each page a `<lastmod>` date, and change it only when the content really changed.
- Declare the sitemap in robots.txt with a `Sitemap:` line, and make sure robots.txt lets Googlebot read the page.
- List only pages that should appear in search: no `noindex` pages, no error pages, no duplicates.
- One address per page. When a page has language versions (for example French), list each one and link them to each other (hreflang).
- New product pages (one per platform or model) go into the sitemap when they are published, so Google finds them even before other pages link to them.

# How the app applies this
- The Web page tab checks Danfoss's robots.txt: whether it can be read, whether it declares a sitemap, and whether Googlebot may read the page.
- Atlas writes `products/<product>/webpage/sitemap.xml` with the reformatted page and the product pages. Each page is listed with its canonical address and the date its file last changed. Product page addresses are proposals until the web team publishes them.
