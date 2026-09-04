#!/usr/bin/env python
"""Run a whole collection plan from a YAML file.

    python scripts/collect_code.py --plan configs/datasets/sources.yaml
    python scripts/collect_code.py --plan configs/datasets/sources.yaml --accept-terms

Local sources run unconditionally. External sources run only when the plan marks
them ``enabled: true`` **and** you passed ``--accept-terms`` on the command line.
Enabling an entry in a file is not consent on its own; the flag is.

See configs/datasets/sources.example.yaml for the plan format.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table
from app.services.datasets import (
    DEFAULT_ALLOWED_LICENSES,
    EXTERNAL_SOURCES,
    SUPPORTED_LANGUAGES,
    CollectionOptions,
    collect_huggingface,
    collect_local_code,
    collect_local_english,
)


def _resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def run_local(entry: dict, output_dir: Path) -> int:
    name = entry.get("name", "local")
    roots = [_resolve(path) for path in entry.get("paths", [])]
    existing = [root for root in roots if root.exists()]
    if not existing:
        print(f"  skipping '{name}': none of its paths exist")
        return 0

    options = CollectionOptions(
        name=name,
        output_path=output_dir / f"{name}.jsonl",
        languages=tuple(entry.get("languages", SUPPORTED_LANGUAGES)),
        max_records=int(entry.get("max_records", 5000)),
        max_file_bytes=int(entry.get("max_file_bytes", 512 * 1024)),
        allowed_licenses=tuple(entry.get("allowed_licenses", DEFAULT_ALLOWED_LICENSES)),
        require_license=bool(entry.get("require_license", True)),
    )

    if entry.get("source") == "local_english":
        written, _ = collect_local_english(existing, options)
    else:
        written, _ = collect_local_code(existing, options)

    print(f"  {name}: {written} records -> {options.output_path}")
    return written


def run_external(entry: dict, output_dir: Path, accepted: bool) -> int:
    name = entry.get("name", "external")
    source = entry.get("source", "")

    if not entry.get("enabled", False):
        print(f"  skipping '{name}': not enabled in the plan")
        return 0
    if source not in EXTERNAL_SOURCES:
        print(f"  skipping '{name}': unknown source '{source}'")
        return 0
    if not accepted:
        terms = entry.get("terms_url") or EXTERNAL_SOURCES[source]["terms_url"]
        print(f"  skipping '{name}': needs --accept-terms  (terms: {terms})")
        return 0

    options = CollectionOptions(
        name=name,
        output_path=output_dir / f"{name}.jsonl",
        max_records=int(entry.get("max_records", 2000)),
        accept_terms=True,
        dataset_name=entry.get("hf_dataset"),
        dataset_config=entry.get("hf_config"),
        split=entry.get("split", "train"),
    )
    written, _ = collect_huggingface(source, options)
    print(f"  {name}: {written} records -> {options.output_path}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--plan", required=True, help="Path to the YAML collection plan.")
    parser.add_argument(
        "--accept-terms",
        action="store_true",
        help="Consent to download from the external hosts named in the plan.",
    )
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)

    plan_path = _resolve(args.plan)
    if not plan_path.exists():
        print(f"error: no plan at {plan_path}", file=sys.stderr)
        return 2

    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    output_dir = _resolve(args.output_dir or plan.get("output_dir", "data/datasets"))
    output_dir.mkdir(parents=True, exist_ok=True)

    print_header(f"Collection plan: {plan_path.name}")
    print_table({"output directory": output_dir, "external downloads": args.accept_terms})

    total = 0
    print("\nLocal sources")
    for entry in plan.get("local", []):
        total += run_local(entry, output_dir)

    print("\nExternal sources")
    for entry in plan.get("external", []):
        total += run_external(entry, output_dir, args.accept_terms)

    print(f"\nCollected {total} records in total.")
    print("Review each manifest before redistributing anything or publishing weights.")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
