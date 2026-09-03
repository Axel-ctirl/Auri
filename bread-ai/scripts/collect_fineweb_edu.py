#!/usr/bin/env python
"""Collect a small English sample from FineWeb-Edu.

FineWeb-Edu is web-crawled text filtered for educational value. It is useful
when you want the model to hold its register in plain English rather than
lapsing into code style mid-sentence.

    python scripts/collect_fineweb_edu.py --max-records 2000 --accept-terms

It is still web-scale crawled data, with the risks that implies: copyrighted
passages, personal information and pages of low quality that survived the
filter. Sample small, read some of what you collected, and prefer your own
writing when you have enough of it.
"""

from __future__ import annotations

from _bootstrap import REPO_ROOT  # noqa: F401
from _external import build_parser, run

SOURCE = "fineweb_edu"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(SOURCE, __doc__ or "")
    parser.set_defaults(config="sample-10BT", max_records=2000)
    return run(SOURCE, parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
