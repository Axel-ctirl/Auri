#!/usr/bin/env python
"""Remove exact and near-duplicate records from a JSONL dataset.

    python scripts/dedupe_dataset.py --input data/datasets/local_code.jsonl
    python scripts/dedupe_dataset.py --input raw.jsonl --threshold 0.9 --exact-only

Exact duplicates are found by hashing whitespace-normalised text. Near
duplicates use a MinHash sketch over word 5-grams, which catches the same file
copied between projects with a header changed.

Duplicates matter more than they look: a model trained on a corpus with heavy
duplication memorises rather than generalises, and the duplicated passages are
exactly what it will reproduce verbatim.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header, print_table

from app.services.datasets.quality import dedupe_records
from app.services.datasets.records import read_jsonl, write_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Sketch similarity above which two records count as duplicates.",
    )
    parser.add_argument("--exact-only", action="store_true", help="Skip near-duplicate detection.")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"error: no file at {input_path}")
        return 2
    output_path = (
        Path(args.output).expanduser() if args.output else input_path.with_suffix(".dedup.jsonl")
    )

    records = [record for _n, record, error in read_jsonl(input_path) if record and not error]
    kept, stats = dedupe_records(
        records, near_duplicates=not args.exact_only, similarity_threshold=args.threshold
    )
    written = write_jsonl(output_path, kept)

    print_header(f"Deduplicating {input_path.name}")
    print_table({**stats.as_dict(), "written": written, "output": output_path})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
