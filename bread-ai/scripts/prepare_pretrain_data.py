#!/usr/bin/env python
"""Train a tokenizer and pack a corpus for pretraining Bread from scratch.

    python scripts/prepare_pretrain_data.py \
        --input data/datasets/local_code.jsonl \
        --input-dir ~/Documents/notes \
        --vocab-size 32000

Two things happen here. A byte-level BPE tokenizer is trained on your text, so
the vocabulary is spent on the identifiers and words you actually use. Then the
whole corpus is tokenized once and written to a flat binary file that training
memory-maps, which is how a corpus larger than RAM is possible at all.

Sources
-------
``--input`` takes any JSONL Bread produced: collected code, English, or an SFT
set. ``--input-dir`` walks a folder for text and source files. Both can be
repeated and are concatenated.

How much data do you need? Roughly 20 tokens per parameter for a
compute-optimal model, and a token is about four characters. A 110M model wants
about 2.2 billion tokens, which is roughly 9 GB of text. Below that you are
better off with a smaller model on the same data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

from _bootstrap import REPO_ROOT, print_header, print_table
from app.services.datasets.collect import SKIP_DIRECTORIES
from app.services.datasets.records import read_jsonl, record_text
from app.services.pretrain import load_tokenizer, pack_documents, train_tokenizer

TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".rst", ".py", ".java", ".js", ".jsx", ".ts",
    ".tsx", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb",
    ".sql", ".sh", ".lua", ".luau", ".html", ".css", ".yaml", ".yml", ".json",
}


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def iter_documents(jsonl_inputs: list[str], directories: list[str]) -> Iterator[str]:
    for raw in jsonl_inputs:
        path = resolve(raw)
        if not path.exists():
            print(f"  warning: no file at {path}, skipping", file=sys.stderr)
            continue
        for _line, record, error in read_jsonl(path):
            if error or record is None:
                continue
            text = record_text(record)
            if text.strip():
                yield text

    for raw in directories:
        root = resolve(raw)
        if not root.exists():
            print(f"  warning: no directory at {root}, skipping", file=sys.stderr)
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIRECTORIES for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if text.strip():
                yield text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", action="append", default=[], help="A JSONL dataset. Repeatable.")
    parser.add_argument(
        "--input-dir", action="append", default=[], dest="input_dirs",
        help="A folder of text or source files. Repeatable.",
    )
    parser.add_argument("--output-dir", default="data/pretrain")
    parser.add_argument("--vocab-size", type=int, default=32000)
    parser.add_argument("--min-frequency", type=int, default=2)
    parser.add_argument(
        "--max-document-tokens", type=int, default=None,
        help="Truncate very long documents, so one huge file cannot dominate.",
    )
    parser.add_argument(
        "--skip-tokenizer", action="store_true",
        help="Reuse the tokenizer already in --output-dir and only repack.",
    )
    args = parser.parse_args(argv)

    if not args.input and not args.input_dirs:
        parser.error("give at least one --input or --input-dir")

    output_dir = resolve(args.output_dir)
    tokenizer_dir = output_dir / "tokenizer"
    corpus_path = output_dir / "corpus.bin"

    print_header("Preparing a pretraining corpus")
    print_table(
        {
            "jsonl inputs": ", ".join(args.input) or "(none)",
            "directories": ", ".join(args.input_dirs) or "(none)",
            "vocabulary": args.vocab_size,
            "tokenizer": tokenizer_dir,
            "corpus": corpus_path,
        }
    )

    if not args.skip_tokenizer:
        print("\nTraining the tokenizer. This reads the corpus once.\n")
        train_tokenizer(
            iter_documents(args.input, args.input_dirs),
            tokenizer_dir,
            vocab_size=args.vocab_size,
            min_frequency=args.min_frequency,
        )
    elif not (tokenizer_dir / "tokenizer.json").exists():
        print(f"error: --skip-tokenizer was given but {tokenizer_dir} has none.", file=sys.stderr)
        return 2

    tokenizer = load_tokenizer(tokenizer_dir)

    print("Packing. This reads the corpus a second time and writes token ids.\n")
    result = pack_documents(
        iter_documents(args.input, args.input_dirs),
        tokenizer,
        corpus_path,
        args.vocab_size,
        max_document_tokens=args.max_document_tokens,
    )

    (output_dir / "corpus.json").write_text(
        json.dumps({**result.as_dict(), "vocab_size": args.vocab_size}, indent=2),
        encoding="utf-8",
    )

    print_header("Result")
    print_table(
        {
            "documents": f"{result.document_count:,}",
            "tokens": f"{result.token_count:,}",
            "corpus size": f"{corpus_path.stat().st_size / 1024**2:.1f} MB",
            "truncated": result.truncated_documents,
        }
    )

    optimal = result.token_count // 20
    print(
        f"\n  At roughly 20 tokens per parameter, this corpus is compute-optimal\n"
        f"  for a model of about {optimal / 1e6:.0f}M parameters. A larger model\n"
        f"  would be undertrained on it; a smaller one leaves capability unused."
    )
    print("\nNext:")
    print("  python scripts/pretrain_bread.py --config configs/pretrain/bread_small.yaml --dry-run")
    return 0 if result.token_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
