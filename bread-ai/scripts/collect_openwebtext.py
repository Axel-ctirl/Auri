#!/usr/bin/env python
"""Collect an experimental English sample from OpenWebText.

OpenWebText is a community reconstruction of the corpus behind GPT-2, built from
outbound Reddit links. Treat it as research material: per-document provenance is
unclear, quality varies widely, and it is the least defensible of Bread's
optional English sources.

    python scripts/collect_openwebtext.py --max-records 1000 --accept-terms

Prefer your own writing, then FineWeb-Edu, then this.
"""

from __future__ import annotations

from _bootstrap import REPO_ROOT  # noqa: F401
from _external import build_parser, run

SOURCE = "openwebtext"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(SOURCE, __doc__ or "")
    parser.set_defaults(max_records=1000)
    return run(SOURCE, parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
