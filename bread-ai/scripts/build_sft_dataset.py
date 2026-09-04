#!/usr/bin/env python
"""Merge collected datasets into one training file, then clean and split it.

    python scripts/build_sft_dataset.py \
        --input data/datasets/local_code.jsonl \
        --input data/datasets/codesearchnet.jsonl \
        --output data/datasets/bread_sft.jsonl \
        --eval-ratio 0.02

Raw-text records are converted into chat records so one training run can use a
mixed corpus. Provenance in ``meta`` is preserved through every step.

The eval split is held out before shuffling is applied to the training half, so
a near-duplicate cannot appear on both sides.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from _bootstrap import print_header, print_table, resolve_output
from app.services.datasets.quality import clean_records, dedupe_records
from app.services.datasets.records import detect_schema, read_jsonl, write_jsonl

TEXT_TO_CHAT_SYSTEM = (
    "You are Bread, a local coding assistant. Continue the user's text in the "
    "same register and style."
)


def to_chat_record(record: dict) -> dict | None:
    """Normalise any supported record shape into sft_chat."""

    schema_name = detect_schema(record)
    meta = record.get("meta", {})

    if schema_name == "sft_chat":
        return record

    if schema_name == "sft_instruction":
        user = record["instruction"]
        if record.get("input"):
            user = f"{user}\n\n{record['input']}"
        return {
            "messages": [
                {"role": "user", "content": user},
                {"role": "assistant", "content": record["output"]},
            ],
            "meta": meta,
        }

    if schema_name == "raw_text":
        text = record["text"]
        split_at = max(len(text) // 4, 200)
        prompt, continuation = text[:split_at], text[split_at:]
        if not continuation.strip():
            return None
        return {
            "messages": [
                {"role": "system", "content": TEXT_TO_CHAT_SYSTEM},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": continuation},
            ],
            "meta": meta,
        }

    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", action="append", required=True, dest="inputs")
    parser.add_argument("--output", default=None)
    parser.add_argument("--eval-ratio", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--no-dedupe", action="store_true")
    args = parser.parse_args(argv)

    output_path = resolve_output(args.output, "bread_sft.jsonl")

    collected: list[dict] = []
    print_header("Reading inputs")
    for raw in args.inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            print(f"  skipping {path}: not found")
            continue
        before = len(collected)
        for _n, record, error in read_jsonl(path):
            if error or record is None:
                continue
            converted = to_chat_record(record)
            if converted is not None:
                collected.append(converted)
        print(f"  {path.name}: {len(collected) - before} records")

    if not collected:
        print("\nerror: nothing to build from.")
        return 1

    if not args.no_clean:
        collected, clean_stats = clean_records(collected)
        print_header("Cleaning")
        print_table(clean_stats.as_dict())

    if not args.no_dedupe:
        collected, dedupe_stats = dedupe_records(collected)
        print_header("Deduplicating")
        print_table(dedupe_stats.as_dict())

    rng = random.Random(args.seed)
    rng.shuffle(collected)
    if args.max_records:
        collected = collected[: args.max_records]

    eval_count = int(len(collected) * max(args.eval_ratio, 0.0))
    eval_records = collected[:eval_count]
    train_records = collected[eval_count:]

    written = write_jsonl(output_path, train_records)
    eval_path = output_path.with_name(output_path.stem + ".eval.jsonl")
    eval_written = write_jsonl(eval_path, eval_records) if eval_records else 0

    print_header("Result")
    print_table(
        {
            "train records": written,
            "train file": output_path,
            "eval records": eval_written,
            "eval file": eval_path if eval_written else "(none)",
        }
    )
    print("\nNext:")
    print(f"  python scripts/validate_dataset.py --input {output_path}")
    print(f"  python scripts/dataset_report.py --input {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
