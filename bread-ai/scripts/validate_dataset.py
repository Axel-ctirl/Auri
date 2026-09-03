#!/usr/bin/env python
"""Validate a JSONL dataset against one of Bread's record schemas.

    python scripts/validate_dataset.py --input data/datasets/bread_sft.jsonl
    python scripts/validate_dataset.py --input notes.jsonl --schema raw_text

Schemas:

  sft_chat          {"messages": [{"role": ..., "content": ...}, ...], "meta": {...}}
  sft_instruction   {"instruction": ..., "input": ..., "output": ..., "meta": {...}}
  raw_text          {"text": ..., "meta": {...}}

Run this before every training run. A malformed record does not fail loudly
during training; it silently teaches the model something you did not intend.

Exit code is 1 when anything is invalid.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header, print_table

from app.services.datasets.quality import validate_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--schema",
        default="sft_chat",
        choices=["sft_chat", "sft_instruction", "raw_text"],
    )
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--show-issues", type=int, default=25)
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"error: no file at {input_path}")
        return 2

    report = validate_file(input_path, args.schema, max_records=args.max_records)

    print_header(f"Validating {input_path.name} as {args.schema}")
    print_table(
        {
            "total records": report.total_records,
            "valid": report.valid_records,
            "invalid": report.invalid_records,
            "duplicates": report.duplicate_records,
            "possible secrets": report.secret_hits,
        }
    )

    if report.issues:
        print_header(f"First {min(args.show_issues, len(report.issues))} issues")
        for issue in report.issues[: args.show_issues]:
            print(f"  line {issue['line']}: {issue['problem']}")

    if report.invalid_records:
        print("\nFix or drop the invalid records before training:")
        print(f"  python scripts/clean_dataset.py --input {input_path}")
        return 1
    if report.secret_hits:
        print("\nCredentials were detected. Redact them before training:")
        print(f"  python scripts/clean_dataset.py --input {input_path}")
        return 1

    print("\nThe dataset is well formed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
