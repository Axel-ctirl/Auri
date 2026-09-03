#!/usr/bin/env python
"""Scan files or a JSONL dataset for credentials.

    python scripts/scan_secrets.py --path ~/projects/my-bot
    python scripts/scan_secrets.py --dataset data/datasets/local_code.jsonl

Findings print the pattern name and the line, never the secret itself. This is a
filter, not a guarantee: read anything you plan to publish.

Exit code is 1 when anything was found, so it works in a pre-commit hook or CI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header

from app.services.datasets.collect import SKIP_DIRECTORIES
from app.services.datasets.records import read_jsonl, record_text
from app.services.datasets.secrets import scan_text

TEXT_SUFFIXES = {
    ".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".sql", ".sh", ".lua", ".luau",
    ".yaml", ".yml", ".json", ".md", ".txt", ".env", ".ini", ".toml", ".cfg",
}


def scan_path(root: Path) -> int:
    findings = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for finding in scan_text(text):
            print(f"  {path}:{finding.line}  {finding.pattern}  {finding.preview}")
            findings += 1
    return findings


def scan_dataset(path: Path) -> int:
    findings = 0
    for line_number, record, error in read_jsonl(path):
        if error or record is None:
            continue
        for finding in scan_text(record_text(record)):
            print(f"  record {line_number}  {finding.pattern}  {finding.preview}")
            findings += 1
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--path", action="append", default=[], dest="paths")
    parser.add_argument("--dataset", action="append", default=[], dest="datasets")
    args = parser.parse_args(argv)

    if not args.paths and not args.datasets:
        parser.error("give at least one --path or --dataset")

    total = 0
    for raw in args.paths:
        root = Path(raw).expanduser()
        print_header(f"Scanning {root}")
        total += scan_path(root)

    for raw in args.datasets:
        dataset = Path(raw).expanduser()
        print_header(f"Scanning {dataset}")
        total += scan_dataset(dataset)

    print_header("Summary")
    if total:
        print(f"  {total} possible credential(s) found.")
        print("  Rotate anything that is real, then re-run the collector; it skips")
        print("  files that trip these patterns.")
        return 1
    print("  Nothing matched. That is not proof the data is clean, only that these")
    print("  patterns did not fire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
