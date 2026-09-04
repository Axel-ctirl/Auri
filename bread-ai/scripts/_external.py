"""Shared argument parsing and execution for external dataset collectors.

Every external source downloads from a host outside your machine, so all of
them require ``--accept-terms``. That flag is not a formality: it is the point
at which you confirm you have read the upstream terms and decided they fit what
you intend to do with the result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _bootstrap import print_header, print_table, resolve_output
from app.services.datasets import (
    DEFAULT_ALLOWED_LICENSES,
    EXTERNAL_SOURCES,
    CollectionOptions,
    TermsNotAcceptedError,
    collect_huggingface,
)


def build_parser(source: str, description: str) -> argparse.ArgumentParser:
    descriptor = EXTERNAL_SOURCES.get(source, {})
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Upstream dataset: {descriptor.get('dataset_name', 'n/a')}\n"
            f"Terms:            {descriptor.get('terms_url', 'n/a')}\n\n"
            "Read the terms before passing --accept-terms. A permissive label on "
            "a dataset does not make every record inside it safe for every use, "
            "and redistribution, commercial use and publishing fine-tuned weights "
            "are three separate questions."
        ),
    )
    parser.add_argument("--name", default=source, help="Dataset name, used for the filename.")
    parser.add_argument("--output", default=None, help="Output .jsonl path.")
    parser.add_argument(
        "--accept-terms",
        action="store_true",
        help="Required. Confirms you have read the upstream terms linked above.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=2000,
        help="Hard cap on records. Bread streams the dataset, so this also caps "
        "how much is downloaded.",
    )
    parser.add_argument(
        "--max-record-bytes",
        type=int,
        default=256 * 1024,
        help="Skip individual records larger than this.",
    )
    parser.add_argument("--hf-dataset", default=None, help="Override the dataset id.")
    parser.add_argument("--config", default=None, help="Dataset configuration or subset.")
    parser.add_argument("--split", default="train")
    parser.add_argument(
        "--allow-license",
        action="append",
        default=[],
        metavar="LICENSE_ID",
        help="Add a license id to the allowlist. Repeat for several.",
    )
    parser.add_argument(
        "--allow-unlicensed",
        action="store_true",
        help="Keep records whose license field is missing or unrecognised.",
    )
    parser.add_argument(
        "--keep-secrets",
        action="store_true",
        help="Do not drop records that look like they contain credentials.",
    )
    return parser


def run(source: str, args: argparse.Namespace) -> int:
    descriptor = EXTERNAL_SOURCES.get(source, {})

    if not args.accept_terms:
        print(
            f"error: collecting '{source}' downloads data from {descriptor.get('source_url', 'an external host')}.\n"
            f"       Read the terms at {descriptor.get('terms_url', 'the dataset page')}\n"
            "       and re-run with --accept-terms once you have.",
            file=sys.stderr,
        )
        return 2

    output_path = resolve_output(args.output, f"{args.name}.jsonl")
    options = CollectionOptions(
        name=args.name,
        output_path=output_path,
        max_records=args.max_records,
        max_file_bytes=args.max_record_bytes,
        allowed_licenses=tuple(DEFAULT_ALLOWED_LICENSES) + tuple(args.allow_license),
        require_license=not args.allow_unlicensed,
        skip_secrets=not args.keep_secrets,
        accept_terms=True,
        dataset_name=args.hf_dataset,
        dataset_config=args.config,
        split=args.split,
    )

    print_header(f"Collecting {source}")
    print_table(
        {
            "dataset": args.hf_dataset or descriptor.get("dataset_name", ""),
            "config": args.config or "(default)",
            "split": args.split,
            "max records": args.max_records,
            "output": output_path,
            "terms": descriptor.get("terms_url", ""),
        }
    )
    print("\nStreaming. This stops as soon as the record cap is reached.\n")

    try:
        written, manifest = collect_huggingface(source, options)
    except TermsNotAcceptedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    print_header("Result")
    print_table(
        {
            "records written": written,
            "output": output_path,
            "manifest": Path(str(output_path)).with_suffix(".manifest.json"),
            "licenses": manifest.license_summary or "(none recorded)",
            "languages": manifest.language_summary or "(none recorded)",
            "skipped (license)": manifest.configuration.get("skipped_for_license", 0),
            "skipped (secrets)": manifest.configuration.get("skipped_for_secrets", 0),
        }
    )
    for warning in manifest.warnings:
        print(f"\n  warning: {warning}")
    return 0 if written else 1
