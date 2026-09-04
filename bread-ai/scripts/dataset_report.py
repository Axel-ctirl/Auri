#!/usr/bin/env python
"""Summarise a JSONL dataset: size, languages, licenses, length distribution.

    python scripts/dataset_report.py --input data/datasets/bread_sft.jsonl
    python scripts/dataset_report.py --input bread_sft.jsonl --json

Read this before you start a training run. The two numbers that matter most are
the record count (a few thousand good examples beats a hundred thousand
mediocre ones) and the p99 length (anything above your configured
max_seq_length gets truncated, which teaches the model to stop mid-thought).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import print_header, print_table
from app.services.datasets.quality import build_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--max-records", type=int, default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"error: no file at {input_path}")
        return 2

    report = build_report(input_path, max_records=args.max_records)

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0

    print_header(f"Report for {input_path.name}")
    print_table(
        {
            "records": report["total_records"],
            "characters": f"{report['total_characters']:,}",
            "approx tokens": f"{report['approx_tokens']:,}",
        }
    )

    if report["language_counts"]:
        print_header("Languages")
        print_table(report["language_counts"])
    if report["license_counts"]:
        print_header("Licenses")
        print_table(report["license_counts"])
    if report["source_counts"]:
        print_header("Sources")
        print_table(report["source_counts"])
    if report["length_percentiles"]:
        print_header("Record length in characters")
        print_table(
            {key: int(value) for key, value in report["length_percentiles"].items()}
        )

    if report["warnings"]:
        print_header("Warnings")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
