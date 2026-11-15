"""
The Wiki tab: read and edit the product's wiki (its OKF bundle) inside Atlas.

The wiki is the single source of truth for every page Atlas writes, so a save is careful:
  - only .md files inside the product's wiki folder can be written;
  - after writing, the whole bundle is loaded again the way the page writer loads it; if
    that fails (for example a missing `type:` in the frontmatter), the old text is put back
    and the save is refused with the reason;
  - numbers that were not in the file before are reported, because a new figure needs a
    Danfoss source (wiki/policies/source-of-truth.md);
  - every save is noted in log.md, newest first under today's date, like the team does;
  - the website copy is rebuilt by the caller, so pages with {{wiki: ...}} blocks follow.

Also: which original documents the wiki cites, and which of them are saved in raw/.
"""
import datetime
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "lab"))
import generate_variants as gv  # noqa: E402

import products  # noqa: E402

WIKI_REF_RE = re.compile(r"\{\{\s*wiki:\s*([^}#\s]+)")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*\.md$")


def _root(p):
    return products.wiki_dir(p)


def _path(p, rel, must_exist=True):
    root = _root(p)
    if root.is_file():  # a single-file fact sheet
        if rel != root.name:
            raise ValueError("This product's wiki is one file")
        return root
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not NAME_RE.match(rel):
        raise ValueError("A wiki file name is lower case, with - between words, and ends in .md "
                         "(for example technologies/new-plate.md)")
    path = (root / rel).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("Only files inside the wiki can be edited")
    if must_exist and not path.is_file():
        raise ValueError(f"No wiki file {rel}")
    return path


def _used_by(p):
    """{wiki ref (path without .md): [page ids of the website copy that include it]}."""
    site = p["folder"] / "webpage" / "site"
    out = {}
    if site.is_dir():
        for f in sorted(site.glob("*/page.md")):
            for ref in set(WIKI_REF_RE.findall(f.read_text(encoding="utf-8", errors="replace"))):
                out.setdefault(ref.strip().removesuffix(".md"), []).append(f.parent.name)
    return out


def files(p):
    """The wiki's files with their title, type and where the website copy uses them."""
    root = _root(p)
    if root.is_file():
        text = root.read_text(encoding="utf-8", errors="replace")
        return {"single": True, "root": root.relative_to(REPO).as_posix(),
                "files": [{"path": root.name, "title": root.stem, "type": "Fact sheet", "description": "",
                           "words": len(text.split()), "used_by": [], "special": False}]}
    used = _used_by(p)
    out = []
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        fm, _ = gv.parse_concept(text)
        fm = fm or {}
        special = f.name in ("index.md", "log.md")
        out.append({"path": rel, "title": fm.get("title") or ("Change log" if f.name == "log.md" else
                    "Index" if f.name == "index.md" else f.stem.replace("-", " ")),
                    "type": fm.get("type") or ("" if special else "no type!"),
                    "description": fm.get("description") or "", "words": len(text.split()),
                    "used_by": used.get(rel.removesuffix(".md"), []), "special": special})
    return {"single": False, "root": root.relative_to(REPO).as_posix(), "files": out}


def read(p, rel):
    return {"path": rel, "text": _path(p, rel).read_text(encoding="utf-8")}


def log_text(p):
    root = _root(p)
    f = root / "log.md" if root.is_dir() else None
    return f.read_text(encoding="utf-8") if f and f.is_file() else ""


def _log(p, rel, created, note):
    root = _root(p)
    if root.is_file():
        return
    f = root / "log.md"
    today = datetime.date.today().isoformat()
    entry = (f"* **{'Creation' if created else 'Update'}** (edited in the Atlas app): `{rel}`."
             + (f" {note.strip().rstrip('.')}." if note.strip() else ""))
    lines = f.read_text(encoding="utf-8").splitlines() if f.is_file() else ["# Directory Update Log", ""]
    head = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)
    if head is not None and lines[head].strip() == f"## {today}":
        lines.insert(head + 1, entry)
    else:
        at = head if head is not None else len(lines)
        lines[at:at] = [f"## {today}", entry, ""]
    f.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def save(p, rel, text, note="", create=False):
    """Write one wiki file, check the bundle still loads, log it. Returns what changed."""
    path = _path(p, rel, must_exist=not create)
    if create and path.exists():
        raise ValueError(f"{rel} already exists: open it in the list instead")
    if path.name == "log.md":
        raise ValueError("log.md is written by Atlas and by hand outside the app, not here")
    text = text.replace("\r\n", "\n").rstrip() + "\n"
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    if old == text:
        return {"changed": False, "new_numbers": [], "removed_numbers": []}
    if path.name != "index.md" and _root(p).is_dir():
        fm, _ = gv.parse_concept(text)
        if not fm or not fm.get("type"):
            raise ValueError("A wiki concept starts with frontmatter that has a type, for example:\n"
                             "---\ntype: Technology\ntitle: New plate\ndescription: One line.\n---")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        products.fact_sheet(p)  # the bundle must still load the way the page writer loads it
    except (ValueError, SystemExit) as e:
        if old is None:
            path.unlink()
        else:
            path.write_text(old, encoding="utf-8")
        raise ValueError(f"Not saved: the wiki would no longer load ({e})")
    before, after = gv.norm_numbers(old or ""), gv.norm_numbers(text)
    _log(p, rel if _root(p).is_dir() else path.name, old is None, note)
    return {"changed": True, "created": old is None,
            "new_numbers": sorted(after - before, key=len), "removed_numbers": sorted(before - after, key=len)}


# --- original documents (raw/) ---------------------------------------------------------------
def raw_dir(p):
    return REPO / p["raw_dir"] if p.get("raw_dir") else p["folder"] / "raw"


def raw_status(p):
    import fetch_raw  # lab/fetch_raw.py
    root = _root(p)
    urls = fetch_raw.source_urls(root if root.is_dir() else root.parent) if root.exists() else []
    out = raw_dir(p)
    rows = []
    for u in urls:
        f = out / f"{fetch_raw.raw_id(u)}.md"
        rows.append({"url": u, "file": f.name, "saved": f.is_file(),
                     "words": len(f.read_text(encoding="utf-8", errors="replace").split()) if f.is_file() else 0})
    by_hand = [f.name for f in sorted(out.glob("*.md")) if f.name.lower() != "readme.md"
               and f.name not in {r["file"] for r in rows}] if out.is_dir() else []
    return {"folder": out.relative_to(REPO).as_posix(), "sources": rows, "other_files": by_hand,
            "used_by_writer": bool(p.get("raw_dir"))}


def update_raw(p, log):
    """Download the documents the wiki cites into raw/ (lab/fetch_raw.py), with its output in the log."""
    import contextlib
    import fetch_raw

    class W:
        buf = ""

        def write(self, s):
            self.buf += s
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                if line.strip():
                    log(line.rstrip())

        def flush(self):
            pass
    root = _root(p)
    out = raw_dir(p)
    argv = sys.argv
    sys.argv = ["fetch_raw.py", "--wiki", str(root if root.is_dir() else root.parent), "--out", str(out)]
    try:
        with contextlib.redirect_stdout(W()):
            fetch_raw.main()
    finally:
        sys.argv = argv
    if not p.get("raw_dir"):  # from now on the writer and the fact check use these documents too
        import json
        f = p["folder"] / "product.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        data["raw_dir"] = out.relative_to(REPO).as_posix()
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"product.json: raw_dir set to {data['raw_dir']}, so the writer and the fact check use it")
