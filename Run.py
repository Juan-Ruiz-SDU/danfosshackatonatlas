#!/usr/bin/env python3
"""
Run the page generator with this project's settings.

  python Run.py                                  Micro Plate pages (default product)
  python Run.py --product motorprotector         INT69 G motor protector pages
  python Run.py --host http://<server-ip>:11434  use the Ollama server on another computer
                                                 (find its IP with `ipconfig` on that computer)
  python Run.py --styles plain,stats             only some styles
  python Run.py --help                           all options

By default each style is filled up to 3 pages (plain_1..3, stats_1..3, ...):
pages that already exist are kept and only checked, so an interrupted run
picks up where it stopped. Any option you pass overrides the defaults below.
Works from any terminal folder: paths are resolved relative to this file.
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent

# One entry per product: its fact sheet, the page topic and its own output folder.
PRODUCTS = {
    "microplate": {
        "--wiki": "wiki",
        "--topic": "Danfoss Micro Plate brazed plate heat exchangers for heat pumps",
        "--out": "variants ManuJuan",
    },
    "motorprotector": {
        "--wiki": "wiki_motor_protector.md",
        "--topic": "Danfoss INT69 G motor protector",
        "--out": "variants MotorProtector",
    },
}
DEFAULT_PRODUCT = "microplate"
COMMON = ["--model", "qwen3:8b", "--host", "http://localhost:11434"]
PAGES_PER_STYLE = 3


def check_ollama(host, model):
    """Fail fast with a clear message instead of a traceback mid-run."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=5) as resp:
            names = {m["name"] for m in json.loads(resp.read())["models"]}
    except OSError as e:
        local = any(h in host for h in ("localhost", "127.0.0.1"))
        hint = ("Start the Ollama app and try again." if local else
                "Check that the computer running Ollama is on, is on the same "
                "network as you, and that the address is right.")
        sys.exit(f"Cannot reach Ollama at {host} ({e}).\n{hint}")
    if model not in names and f"{model}:latest" not in names:
        sys.exit(f"Model '{model}' is not installed in Ollama at {host}.\n"
                 f"Installed: {', '.join(sorted(names)) or 'none'}\n"
                 f"Install it with: ollama pull {model}")


def main():
    os.chdir(HERE)
    pick = argparse.ArgumentParser(prog="Run.py", add_help=False)
    pick.add_argument("--product", choices=PRODUCTS, default=DEFAULT_PRODUCT)
    chosen, user_args = pick.parse_known_args()
    wants_help = bool({"-h", "--help"} & set(user_args))
    if wants_help:
        print(f"Products (--product): {', '.join(PRODUCTS)}  "
              f"(default: {DEFAULT_PRODUCT})\n")

    args = [x for pair in PRODUCTS[chosen.product].items() for x in pair] + COMMON
    if not {"--runs", "--target"} & {a.split("=")[0] for a in user_args}:
        args += ["--target", str(PAGES_PER_STYLE)]
    args += user_args  # argparse keeps the last value, so yours win

    if not wants_help:
        p = argparse.ArgumentParser(add_help=False)
        for opt in ("--host", "--model", "--wiki", "--out"):
            p.add_argument(opt)
        opts, _ = p.parse_known_args(args)
        check_ollama(opts.host, opts.model)
        print(f"Product: {chosen.product} | fact sheet: {opts.wiki} | "
              f"output: {opts.out} | Ollama: {opts.host} ({opts.model})\n", flush=True)

    sys.path.insert(0, str(HERE))
    import generate_variants
    sys.argv = ["generate_variants.py"] + args
    generate_variants.main()


if __name__ == "__main__":
    main()
