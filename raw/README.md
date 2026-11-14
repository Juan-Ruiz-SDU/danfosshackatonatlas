# raw/: the original Danfoss sources

The wiki (`wiki/`) is a compiled summary of these documents. Compiling loses detail and caveats, so two
tools also read the originals:

- **The writer** (`generate_variants.py` and the Atlas Run tab) gets the original passages that best
  match the page topic next to the wiki facts. They help it get conditions and caveats right. It may
  not add a fact that is only here.
- **The fact check** (Atlas Web page and Product by product tabs, `app/verify.py`) checks every claim
  of a page against the wiki, these documents and Danfoss's own pages.

Update with `python Run.py update-raw`. It downloads every http(s) source cited in the wiki.

A source with no URL in the wiki, such as the main eBrochure `AD565353287087en-000101`, has to be added
by hand. Drop its PDF here and run `python Run.py update-raw` again, or save its text as `<id>.md` with
the same header as the other files.

Every file is the source's text as downloaded, not edited.
