#!/usr/bin/env python
"""Collect code-and-documentation pairs from CodeSearchNet.

CodeSearchNet pairs a function with its docstring, which makes it a natural fit
for instruction tuning: the docstring becomes the request and the function
becomes the answer.

    python scripts/collect_codesearchnet.py --config python --max-records 3000 --accept-terms

The dataset spans many repositories under many licenses. The per-record license
field is what matters, not the dataset-level label, and Bread filters on it.
"""

from __future__ import annotations

from _external import build_parser, run

from _bootstrap import REPO_ROOT  # noqa: F401  (puts backend/ on sys.path)

SOURCE = "codesearchnet"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(SOURCE, __doc__ or "")
    parser.set_defaults(config="python")
    return run(SOURCE, parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
