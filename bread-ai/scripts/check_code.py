#!/usr/bin/env python
"""Check generated code for references that cannot resolve, without running it.

    python scripts/check_code.py --file answer.py
    python scripts/check_code.py --answer answer.md
    cat answer.md | python scripts/check_code.py

The characteristic failure of a small coding model is not bad logic. It is
fluent, well-structured code that calls something which does not exist. This
catches that class of mistake deterministically, by checking the code against
the libraries actually installed on this machine.

Findings come in two confidences, kept apart on purpose:

``certain``    provably wrong: an undefined name, a missing module attribute, a
               keyword the signature does not accept, too many positional
               arguments to a keyword-only function
``suspected``  an attribute missing from a class that could still set it at
               runtime, so worth checking rather than worth trusting

Exit code is 1 when anything certain is found, so this works in a pre-commit
hook. Suspicions alone do not fail it.

Nothing from the checked code is executed. The libraries it imports are
imported, so that their real signatures can be read; pass ``--no-import`` for a
purely syntactic check that touches nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _bootstrap import print_header, print_table
from app.services.quality.api_check import check_answer, check_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", help="A .py file to check.")
    source.add_argument("--answer", help="A model answer containing fenced code.")
    parser.add_argument(
        "--no-import",
        dest="allow_import",
        action="store_false",
        default=True,
        help="Skip library inspection and check syntax and names only.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if args.file:
        text = Path(args.file).expanduser().read_text(encoding="utf-8")
        report = check_code(text, allow_import=args.allow_import)
        label = args.file
    elif args.answer:
        text = Path(args.answer).expanduser().read_text(encoding="utf-8")
        report = check_answer(text, allow_import=args.allow_import)
        label = args.answer
    else:
        text = sys.stdin.read()
        report = check_answer(text, allow_import=args.allow_import)
        label = "stdin"

    if args.as_json:
        print(json.dumps(report.as_dict(), indent=2))
        return 1 if report.certain else 0

    print_header(f"Checking {label}")
    if report.syntax_error:
        print(f"  syntax error: {report.syntax_error}")
        return 1

    print_table(
        {
            "libraries inspected": ", ".join(report.modules_checked) or "(none)",
            "not installed here": ", ".join(report.modules_unavailable) or "(none)",
        }
    )

    if report.certain:
        print("\nProblems")
        for finding in report.certain:
            print(f"  line {finding.line:>4}  {finding.kind:<10} {finding.message}")

    if report.likely:
        print("\nWorth checking")
        for finding in report.likely:
            print(f"  line {finding.line:>4}  {finding.kind:<10} {finding.message}")

    print()
    if report.certain:
        print(f"  {len(report.certain)} problem(s) that will not run as written.")
    elif report.likely:
        print("  Nothing provably wrong. The suspicions above are worth a look.")
    else:
        print(
            "  Every name and signature in this code resolves against your " "installed libraries."
        )

    if report.modules_unavailable:
        print(
            "\n  Note: "
            + ", ".join(report.modules_unavailable)
            + " is not installed here, so nothing in it could be checked."
        )

    return 1 if report.certain else 0


if __name__ == "__main__":
    raise SystemExit(main())
