#!/usr/bin/env python
"""Clean a JSONL dataset: normalise text, drop junk, redact credentials.

    python scripts/clean_dataset.py --input data/datasets/local_code.jsonl
    python scripts/clean_dataset.py --input raw.jsonl --output clean.jsonl --drop-secret-records

What gets dropped: records that are too short to teach anything, records so long
they will not fit the training sequence, files that announce themselves as
generated, minified bundles, and text that is mostly non-ASCII.

What gets rewritten: line endings, trailing whitespace, runs of blank lines,
and anything matching a credential pattern (replaced with a marker, not deleted,
so the surrounding code still parses).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header, print_table

from app.services.datasets.quality import clean_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--output",
        default=None,
        help="Defaults to <input>.clean.jsonl so the original is never overwritten.",
    )
    parser.add_argument("--no-dedupe", action="store_true", help="Keep duplicates.")
    parser.add_argument(
        "--drop-secret-records",
        action="store_true",
        help="Delete records containing credentials instead of redacting them.",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"error: no file at {input_path}")
        return 2

    output_path = (
        Path(args.output).expanduser()
        if args.output
        else input_path.with_suffix(".clean.jsonl")
    )

    print_header(f"Cleaning {input_path.name}")
    result = clean_file(
        input_path,
        output_path,
        dedupe=not args.no_dedupe,
        drop_secret_records=args.drop_secret_records,
    )

    print_table(result["clean"])
    print()
    print_table(result["dedupe"])
    print()
    print_table({"written": result["written"], "output": output_path})

    if result["written"] == 0:
        print("\nEverything was filtered out. Check the input with:")
        print(f"  python scripts/dataset_report.py --input {input_path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
