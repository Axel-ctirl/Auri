#!/usr/bin/env python
"""Turn prompts/identity.yaml into training records that make a model Bread.

    python scripts/build_identity_dataset.py
    python scripts/build_identity_dataset.py \
        --mix data/datasets/bread_sft.jsonl --mix-ratio 8

Why the mix matters
-------------------
Training on identity data alone is the classic way to ruin a model. A few
hundred records about "who are you" at a normal learning rate will teach it to
answer that question beautifully and to have forgotten how to write a for loop.
The effect is called catastrophic forgetting and it is not subtle.

The fix is to drown the identity data in ordinary work. ``--mix-ratio 8`` puts
eight general coding records beside every identity record, so the gradient signal
is dominated by "keep being a coding model" and identity is a small, consistent
nudge. Eight is a reasonable floor; higher is safer and slower.

Without ``--mix`` this writes identity data on its own, which is useful for
inspecting the corpus and is **not** what you should train on.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table, resolve_output
from app.services.datasets.records import (
    RecordMeta,
    make_chat_record,
    read_jsonl,
    validate_record,
    write_jsonl,
)

DEFAULT_CORPUS = REPO_ROOT / "prompts" / "identity.yaml"


def load_corpus(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        corpus = yaml.safe_load(handle) or {}
    if not isinstance(corpus, dict):
        raise SystemExit(f"{path} must contain a YAML mapping.")
    for key in ("identity", "base_model"):
        if key not in corpus:
            raise SystemExit(f"{path} is missing the '{key}' key.")
    return corpus


def load_system_prompt(corpus: dict[str, Any]) -> str:
    raw = corpus.get("system_prompt_path", "prompts/system_default.md")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        raise SystemExit(f"System prompt not found at {path}.")
    return path.read_text(encoding="utf-8").strip()


PLACEHOLDERS = ("base_model", "base_license", "name")


def substitute(text: str, corpus: dict[str, Any]) -> str:
    """Fill {base_model} and friends so the corpus survives a model swap.

    Plain replacement rather than str.format, because the corpus is full of code
    examples containing literal braces: f-strings, Go structs, and GitHub
    Actions expressions like ${{ github.ref }} would all raise or be mangled.
    """

    for key in PLACEHOLDERS:
        token = "{" + key + "}"
        if token in text:
            text = text.replace(token, str(corpus.get(key, "")))
    return text


def build_records(corpus: dict[str, Any], system_prompt: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def emit(user: str, assistant: str, kind: str) -> None:
        records.append(
            make_chat_record(
                system=system_prompt,
                user=substitute(user, corpus).strip(),
                assistant=substitute(assistant, corpus).strip(),
                meta=RecordMeta(
                    source=f"bread_identity/{kind}",
                    license="USER_OWNED",
                    language="english",
                    notes="Hand-written corpus defining Bread's identity and voice.",
                ),
            )
        )

    for group in corpus.get("identity", []):
        answer = group.get("answer", "")
        for question in group.get("questions", []):
            emit(question, answer, "identity")

    for section, kind in (
        ("style_examples", "style"),
        ("uncertainty_examples", "uncertainty"),
        ("domain_examples", "domain"),
    ):
        for example in corpus.get(section, []) or []:
            emit(example.get("user", ""), example.get("assistant", ""), kind)

    return records


def load_mix(paths: list[str], limit: int | None) -> list[dict[str, Any]]:
    """Read general coding records that keep the fine-tune from narrowing."""

    mixed: list[dict[str, Any]] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            print(f"  warning: no mix file at {path}, skipping", file=sys.stderr)
            continue
        for _line, record, error in read_jsonl(path):
            if error or record is None:
                continue
            if "messages" not in record:
                continue
            mixed.append(record)
            if limit is not None and len(mixed) >= limit:
                return mixed
    return mixed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--output", default=None, help="Defaults to data/datasets/bread_identity.jsonl")
    parser.add_argument(
        "--mix",
        action="append",
        default=[],
        dest="mix",
        help="A general coding dataset to interleave. Repeat for several. "
        "Strongly recommended: see the note at the top of this file.",
    )
    parser.add_argument(
        "--mix-ratio",
        type=int,
        default=8,
        help="General records per identity record. 8 is a sensible floor.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="How many times each identity record appears. Small values only; "
        "repetition is how identity sticks, and also how overfitting starts.",
    )
    parser.add_argument("--eval-ratio", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument(
        "--base-model",
        default=None,
        help="Override the base model named in the corpus, so answers stay truthful "
        "when you bake from a different base.",
    )
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus).expanduser()
    if not corpus_path.is_absolute():
        corpus_path = REPO_ROOT / corpus_path
    corpus = load_corpus(corpus_path)
    if args.base_model:
        corpus["base_model"] = args.base_model

    system_prompt = load_system_prompt(corpus)
    identity_records = build_records(corpus, system_prompt)

    invalid = [
        (index, problems)
        for index, record in enumerate(identity_records)
        if (problems := validate_record(record, "sft_chat"))
    ]
    if invalid:
        print("error: the corpus produced invalid records:", file=sys.stderr)
        for index, problems in invalid[:10]:
            print(f"  record {index}: {'; '.join(problems)}", file=sys.stderr)
        return 1

    output_path = resolve_output(args.output, "bread_identity.jsonl")

    print_header("Building Bread's identity dataset")
    print_table(
        {
            "corpus": corpus_path,
            "base model": corpus.get("base_model", ""),
            "identity records": len(identity_records),
            "repeat": args.repeat,
            "mix files": ", ".join(args.mix) or "(none)",
            "mix ratio": args.mix_ratio,
            "output": output_path,
        }
    )

    repeated = identity_records * max(args.repeat, 1)
    mixed = load_mix(args.mix, limit=len(repeated) * max(args.mix_ratio, 0)) if args.mix else []

    if args.mix and not mixed:
        print(
            "\nerror: --mix was given but no general records were read. Build one "
            "first:\n"
            "  python scripts/collect_local_code.py --path <your projects>\n"
            "  python scripts/build_sft_dataset.py --input <collected>.jsonl",
            file=sys.stderr,
        )
        return 1

    if not args.mix:
        print(
            "\n  warning: no --mix given. Training on identity data alone will\n"
            "  teach the model to introduce itself and to forget how to code.\n"
            "  Pass --mix data/datasets/bread_sft.jsonl before you train on this.\n"
        )

    combined = repeated + mixed
    rng = random.Random(args.seed)
    rng.shuffle(combined)

    eval_count = int(len(combined) * max(args.eval_ratio, 0.0))
    eval_records = combined[:eval_count]
    train_records = combined[eval_count:]

    written = write_jsonl(output_path, train_records)
    eval_path = output_path.with_name(output_path.stem + ".eval.jsonl")
    eval_written = write_jsonl(eval_path, eval_records) if eval_records else 0

    identity_share = len(repeated) / max(len(combined), 1) * 100

    print_header("Result")
    print_table(
        {
            "train records": written,
            "train file": output_path,
            "eval records": eval_written,
            "eval file": eval_path if eval_written else "(none)",
            "identity share": f"{identity_share:.1f}%",
        }
    )

    if identity_share > 30 and args.mix:
        print(
            "\n  warning: identity data is over 30% of the mix. Raise --mix-ratio\n"
            "  or collect more general data, or the model will over-index on\n"
            "  talking about itself."
        )

    print("\nNext:")
    print(f"  python scripts/validate_dataset.py --input {output_path}")
    print(f"  python scripts/dataset_report.py --input {output_path}")
    print("  python scripts/bake_bread_model.py --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
