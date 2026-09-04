#!/usr/bin/env python
"""Collect plain-English text you own: notes, docs, articles you wrote.

    python scripts/collect_english.py --path "~/Documents/notes" --max-records 2000

This is the source to prefer for English. It is yours, its provenance is
obvious, and a model tuned on your writing sounds like your writing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _bootstrap import print_header, print_table, resolve_output
from app.services.datasets import CollectionOptions, collect_local_english


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--name", default="local_english")
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-records", type=int, default=2000)
    parser.add_argument("--max-file-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--keep-secrets", action="store_true")
    args = parser.parse_args(argv)

    roots = [Path(path).expanduser() for path in args.paths]
    missing = [str(root) for root in roots if not root.exists()]
    if missing:
        print(f"error: these paths do not exist: {', '.join(missing)}", file=sys.stderr)
        return 2

    output_path = resolve_output(args.output, f"{args.name}.jsonl")
    written, manifest = collect_local_english(
        roots,
        CollectionOptions(
            name=args.name,
            output_path=output_path,
            max_records=args.max_records,
            max_file_bytes=args.max_file_bytes,
            skip_secrets=not args.keep_secrets,
        ),
    )

    print_header("Result")
    print_table({"records written": written, "output": output_path, "sources": len(roots)})
    for warning in manifest.warnings:
        print(f"\n  warning: {warning}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
