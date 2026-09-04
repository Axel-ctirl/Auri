#!/usr/bin/env python
"""Export a pretrained Bread model into a Transformers-loadable directory.

    python scripts/export_pretrained.py \
        --run data/runs/pretrain-bread-small \
        --tokenizer data/pretrain/tokenizer \
        --output data/models/bread-small

The exported directory carries a model card and a provenance file recording
``trained_from_scratch: true`` and no base model, because there is none.

The result is a base model. It completes text; it does not follow instructions.
Fine-tune it before expecting it to answer questions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT, print_header, print_table
from app.services.pretrain.export import export_to_transformers


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run", required=True, help="A pretraining output directory.")
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--license", default="apache-2.0", dest="license_id")
    parser.add_argument(
        "--data-note",
        default="Collected locally with Bread's dataset tools.",
        help="One line for the model card describing what it was trained on.",
    )
    args = parser.parse_args(argv)

    run_dir = resolve(args.run)
    checkpoint = run_dir / "checkpoint.pt"
    if not checkpoint.exists():
        print(f"error: no checkpoint at {checkpoint}")
        return 2

    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    output = resolve(args.output)
    print_header("Exporting")
    print_table({"checkpoint": checkpoint, "tokenizer": resolve(args.tokenizer), "output": output})

    info = export_to_transformers(
        checkpoint,
        resolve(args.tokenizer),
        output,
        model_name=args.name or output.name,
        license_id=args.license_id,
        data_note=args.data_note,
        summary=summary,
    )

    print_header("Done")
    print_table(
        {
            "parameters": f"{info['parameters']:,}",
            "tensors": info["tensors"],
            "model card": output / "README.md",
            "provenance": output / "bread.json",
        }
    )
    print("\nLoad it in Bread with:")
    print(f"  MODEL_ID={output}")
    print("  MODEL_BACKEND=transformers")
    print("  QUANTIZATION_MODE=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
