---
type: Guideline
title: Crawlability
description: What Googlebot and AI search need from the HTML - content in the first response, a fast and error-free server, clean metadata.
tags: [guideline, googlebot, crawling, technical seo]
applies_to: app
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-11-14T19:30:00Z
---
# What Google says decides how much it crawls
Google Search Central lists the factors behind crawling: how fast the server answers Googlebot's individual requests, the quality of the content, server errors, and other signals. Crawling decides how often a page is read again, not how it ranks. A page that is slow or fails is read less often, so updates reach search and AI answers later.

# Rules for generated pages
- All product content is in the HTML of the first response. Nothing important may need JavaScript: tabs, accordions, "product range" and "documents" blocks that load later are invisible to a crawler that does not run scripts.
- Static HTML, light: no tracking scripts needed to show the text.
- The page answers with status 200 directly. Avoid redirect chains: link to the final URL.
- Keep the server fast. Measure the time to first byte; slow answers mean fewer crawls.
- One `<title>`, one meta description, a canonical link to the final URL, and `lang` on the `<html>` tag.
- No `noindex`, `nosnippet` or `max-snippet:0` on pages that should appear in AI answers.
- Structured data (JSON-LD) only repeats what the page shows, with absolute, working URLs.
- Images have an `alt` text.
- The page is listed in the XML sitemap and robots.txt lets Googlebot read it (see [Sitemap](sitemap.md)).
- Bot protection (a JavaScript challenge or a captcha instead of the page) must let search and AI crawlers through. If our own tools get such a check instead of the page or robots.txt, ask the web team which crawlers are allowed.

# How the app checks this
The "Web page" tab of the Atlas app checks the current Danfoss page once, when it makes the copy:
- status, redirects and response time;
- words visible without JavaScript;
- headings, metadata and structured data;
- robots.txt and the sitemap;
- whether a bot check answered instead of the page.

It then checks your copy the same way.
