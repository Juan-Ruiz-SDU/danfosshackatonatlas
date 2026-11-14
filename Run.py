#!/usr/bin/env python3
"""
Run the page generator with this project's default settings.

  python Run.py                        one page per style, from the wiki/ folder
  python Run.py --runs 3               three pages per style
  python Run.py --styles plain,stats   only some styles
  python Run.py --model llama3.1:8b    another Ollama model
  python Run.py --help                 all options
  python Run.py app                    open the Atlas app in your browser (the whole process)
  python Run.py update-sources         ask prompts/prompts.txt, import the sources Gemini used
  python Run.py update-raw             download the original Danfoss documents the wiki cites into raw/
                                       (see lab/discover_sources.py for its options)

Any option you pass overrides the defaults below. Works from any terminal
folder: paths are resolved relative to this file.
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent

# Edit these to change what a plain `python Run.py` does.
DEFAULTS = [
    "--wiki", "wiki",
    "--topic", "Danfoss Micro Plate brazed plate heat exchangers for heat pumps",
    "--out", "variants ManuJuan",
    "--model", "qwen3:8b",
    "--host", "http://localhost:11434",
    "--runs", "1",
]


def check_ollama(host, model):
    """Fail fast with a clear message instead of a traceback mid-run."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=5) as resp:
            names = {m["name"] for m in json.loads(resp.read())["models"]}
    except OSError as e:
        sys.exit(f"Cannot reach Ollama at {host} ({e}).\n"
                 "Start the Ollama app and try again.")
    if model not in names and f"{model}:latest" not in names:
        sys.exit(f"Model '{model}' is not installed in Ollama at {host}.\n"
                 f"Installed: {', '.join(sorted(names)) or 'none'}\n"
                 f"Install it with: ollama pull {model}")


def main():
    os.chdir(HERE)
    if sys.argv[1:2] == ["app"]:
        # The Atlas app in your browser: runs the whole process, hands you the files.
        sys.path.insert(0, str(HERE / "app"))
        import server
        server.main()
        return
    if sys.argv[1:2] == ["update-raw"]:
        # Download the original Danfoss documents the wiki cites into raw/.
        sys.path.insert(0, str(HERE / "lab"))
        import fetch_raw
        sys.argv = ["fetch_raw.py"] + sys.argv[2:]
        fetch_raw.main()
        return
    if sys.argv[1:2] == ["update-sources"]:
        # Ask the prompts in prompts/prompts.txt and import the sources Gemini used.
        sys.path.insert(0, str(HERE / "lab"))
        import discover_sources
        sys.argv = ["discover_sources.py"] + sys.argv[2:]
        discover_sources.main()
        return
    args = DEFAULTS + sys.argv[1:]  # argparse keeps the last value, so yours win
    if not {"-h", "--help"} & set(args):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--host")
        p.add_argument("--model")
        opts, _ = p.parse_known_args(args)
        check_ollama(opts.host, opts.model)

    sys.path.insert(0, str(HERE))
    import generate_variants
    sys.argv = ["generate_variants.py"] + args
    generate_variants.main()


if __name__ == "__main__":
    main()
