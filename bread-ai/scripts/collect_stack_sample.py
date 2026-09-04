#!/usr/bin/env python
"""Collect a small, filtered sample from The Stack.

The Stack is a very large permissively-licensed source-code corpus. Bread only
ever takes a bounded streamed sample of it, and defaults to the ``the-stack-smol``
subset so an accidental run cannot pull terabytes.

    python scripts/collect_stack_sample.py --config data/python --max-records 2000 --accept-terms

Two things to know before you use this data:

* The Stack has an opt-out process. Authors can request removal, and a snapshot
  you collected earlier will not reflect later removals. Re-check before you
  publish anything derived from it.
* Its license metadata is inferred at scale and is not perfect. Bread filters on
  the per-record license field, which narrows the risk without eliminating it.
"""

from __future__ import annotations

from _external import build_parser, run

from _bootstrap import REPO_ROOT  # noqa: F401

SOURCE = "the_stack"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(SOURCE, __doc__ or "")
    parser.set_defaults(config="data/python", max_records=2000)
    return run(SOURCE, parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
