#!/usr/bin/env python
"""Collect a training dataset from local code you own.

This is the recommended way to build a dataset for Bread. Your own repositories
have licenses you can check, code in the style you actually write, and no terms
of use to accept.

    python scripts/collect_local_code.py \
        --path "C:/dev/minecraft-plugins" \
        --path "~/projects/discord-bot" \
        --languages python java lua \
        --max-records 5000

Files are skipped when their project has no recognised license, when they look
generated or minified, or when they appear to contain credentials. Every record
keeps its provenance in a ``meta`` field, and a manifest is written next to the
output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _bootstrap import REPO_ROOT, print_header, print_table, resolve_output

from app.services.datasets import (
    DEFAULT_ALLOWED_LICENSES,
    SUPPORTED_LANGUAGES,
    CollectionOptions,
    collect_local_code,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a JSONL dataset from local source folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        dest="paths",
        help="A folder to walk. Repeat for several. Subfolders with their own "
        "LICENSE file are treated as separate projects.",
    )
    parser.add_argument("--name", default="local_code", help="Dataset name, used for the filename.")
    parser.add_argument("--output", default=None, help="Output .jsonl path.")
    parser.add_argument(
        "--languages",
        nargs="+",
        default=list(SUPPORTED_LANGUAGES),
        choices=list(SUPPORTED_LANGUAGES),
        help="Languages to include.",
    )
    parser.add_argument("--max-records", type=int, default=5000)
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=512 * 1024,
        help="Skip files larger than this. Big files are usually vendored or generated.",
    )
    parser.add_argument(
        "--allow-license",
        action="append",
        default=[],
        metavar="LICENSE_ID",
        help="Add a license id to the allowlist, e.g. --allow-license MPL-2.0. "
        "Repeat for several. Use deliberately: the default list is the set of "
        "permissive licenses that are least likely to constrain what you do next.",
    )
    parser.add_argument(
        "--allow-unlicensed",
        action="store_true",
        help="Include files whose project has no detectable license. Do not do "
        "this for anything you intend to publish.",
    )
    parser.add_argument(
        "--keep-secrets",
        action="store_true",
        help="Do not skip files that look like they contain credentials. Off by default.",
    )
    parser.add_argument(
        "--raw-text",
        action="store_true",
        help="Emit {'text': ...} records instead of instruction-style chat records.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    roots = [Path(path).expanduser() for path in args.paths]
    missing = [str(root) for root in roots if not root.exists()]
    if missing:
        print(f"error: these paths do not exist: {', '.join(missing)}", file=sys.stderr)
        return 2

    allowed = tuple(DEFAULT_ALLOWED_LICENSES) + tuple(args.allow_license)
    output_path = resolve_output(args.output, f"{args.name}.jsonl")

    options = CollectionOptions(
        name=args.name,
        output_path=output_path,
        languages=tuple(args.languages),
        max_records=args.max_records,
        max_file_bytes=args.max_file_bytes,
        allowed_licenses=allowed,
        require_license=not args.allow_unlicensed,
        skip_secrets=not args.keep_secrets,
        instruction_style=not args.raw_text,
    )

    print_header(f"Collecting {args.name}")
    print_table(
        {
            "paths": ", ".join(str(root) for root in roots),
            "languages": ", ".join(args.languages),
            "allowed licenses": (", ".join(allowed) if not args.allow_unlicensed else "any"),
            "max records": args.max_records,
            "output": output_path,
        }
    )
    print()

    written, manifest = collect_local_code(
        roots,
        options,
        progress=lambda count: print(f"  ... {count} records", flush=True),
    )

    print_header("Result")
    print_table(
        {
            "records written": written,
            "output": output_path,
            "manifest": Path(str(output_path)).with_suffix(".manifest.json"),
            "licenses": manifest.license_summary or "(none matched)",
            "languages": manifest.language_summary or "(none matched)",
            "skipped (license)": manifest.configuration.get("skipped_for_license", 0),
            "skipped (secrets)": manifest.configuration.get("skipped_for_secrets", 0),
        }
    )

    if written == 0:
        print(
            "\nNo records were collected. The usual cause is that no project under "
            "those paths has a LICENSE file Bread recognises. Check with:\n"
            f"  python scripts/license_check.py --path {roots[0]}"
        )
        return 1

    print("\nNext steps:")
    print(f"  python scripts/clean_dataset.py --input {output_path}")
    print(f"  python scripts/validate_dataset.py --input {output_path}")
    print(f"  python scripts/dataset_report.py --input {output_path}")
    print(
        "\nReview the licenses in the manifest before you redistribute this data "
        "or publish weights trained on it."
    )
    print(f"  repository root: {REPO_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
