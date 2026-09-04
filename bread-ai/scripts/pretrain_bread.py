#!/usr/bin/env python
"""Pretrain a Bread model from random initialisation.

    python scripts/pretrain_bread.py --config configs/pretrain/bread_small.yaml --dry-run
    python scripts/pretrain_bread.py --config configs/pretrain/bread_small.yaml

Every weight starts as noise. Nothing is inherited from any other model.

Read docs/PRETRAINING.md before committing days of GPU time. The short version:
one 5090 can honestly pretrain something in the 100M to 800M range, and that
model will be fluent and genuinely yours, and will not match a 7B model trained
on trillions of tokens. Compute and data set that ceiling.

Progress is printed as ``BREAD_PROGRESS {...}`` lines, which the Training page
reads. The run checkpoints regularly and resumes from where it stopped, so an
interrupted run costs minutes rather than days.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table
from app.services.pretrain import PretrainConfig, pretrain
from app.services.pretrain.model import BreadLM, ComputeBudget
from app.services.pretrain.train import resolve_device, resolve_dtype


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def load_config(path: Path, overrides: dict[str, Any]) -> PretrainConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a YAML mapping.")
    payload.update({key: value for key, value in overrides.items() if value is not None})
    return PretrainConfig.from_dict(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--corpus-path", default=None)
    parser.add_argument("--tokenizer-dir", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--run-id", default=None, help="Set by the API; ignored otherwise.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the model, report the compute budget, then stop.",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignore any existing checkpoint.")
    args = parser.parse_args(argv)

    config_path = resolve(args.config)
    if not config_path.exists():
        raise SystemExit(f"error: no config at {config_path}")

    config = load_config(
        config_path,
        {
            "corpus_path": args.corpus_path,
            "tokenizer_dir": args.tokenizer_dir,
            "output_dir": args.output_dir,
            "max_steps": args.max_steps,
            "device": args.device,
        },
    )

    corpus = resolve(config.corpus_path)
    config.corpus_path = str(corpus)
    config.tokenizer_dir = str(resolve(config.tokenizer_dir))
    config.output_dir = str(resolve(config.output_dir))

    try:
        import torch  # noqa: F401
    except ImportError:
        raise SystemExit(
            "error: PyTorch is not installed. See docs/LINUX_SETUP.md or " "docs/WINDOWS_SETUP.md."
        ) from None

    model = BreadLM(config.model_config())
    counts = model.parameter_counts()
    budget = ComputeBudget(parameters=counts["total"], tokens=config.total_tokens)
    device = resolve_device(config.device)

    print_header(f"Pretraining {config.name}")
    print_table(
        {
            "config": config_path,
            "parameters": f"{counts['total']:,}",
            "non-embedding": f"{counts['non_embedding']:,}",
            "layers / hidden": f"{config.num_hidden_layers} / {config.hidden_size}",
            "heads": f"{config.num_attention_heads} ({config.num_key_value_heads} kv)",
            "context": config.sequence_length,
            "vocabulary": f"{config.vocab_size:,}",
            "tokens per step": f"{config.tokens_per_step:,}",
            "planned tokens": f"{config.total_tokens:,}",
            "tokens / parameter": round(config.total_tokens / max(counts["total"], 1), 1),
            "compute-optimal tokens": f"{budget.chinchilla_tokens:,}",
            "device": str(device),
            "dtype": str(resolve_dtype(config.dtype, device)).replace("torch.", ""),
        }
    )

    ratio = config.total_tokens / max(counts["total"], 1)
    if ratio < 10:
        print(
            f"\n  warning: {ratio:.1f} tokens per parameter is well under the ~20 that is\n"
            "  compute-optimal. This model will be undertrained. A smaller model on\n"
            "  the same budget would come out better."
        )

    if not corpus.exists():
        raise SystemExit(
            f"error: no packed corpus at {corpus}.\n"
            "       Build one first:\n"
            "         python scripts/prepare_pretrain_data.py --input <your dataset>.jsonl"
        )

    if args.dry_run:
        print("\nDry run complete. Nothing was trained.")
        return 0

    def on_event(payload: dict[str, Any]) -> None:
        kind = payload.get("event")
        if kind == "step":
            print(
                f"  step {payload['step']:>7}/{payload['total_steps']}  "
                f"loss {payload['loss']:.4f}  ppl {payload['perplexity']:>9.1f}  "
                f"{payload['tokens_per_second']:>9,.0f} tok/s  "
                f"eta {payload['eta_hours']:.1f}h",
                flush=True,
            )
        elif kind == "eval":
            print(
                f"  eval  step {payload['step']}  loss {payload['eval_loss']:.4f}  "
                f"ppl {payload['eval_perplexity']:.1f}",
                flush=True,
            )
        # The Training page parses these.
        print("BREAD_PROGRESS " + json.dumps(_progress(payload)), flush=True)

    summary = pretrain(config, on_event=on_event, resume=not args.no_resume)

    print_header("Done")
    print_table(
        {
            "steps": summary["steps"],
            "tokens seen": f"{summary['tokens_seen']:,}",
            "final loss": summary["final_loss"],
            "held-out loss": summary["eval_loss"],
            "held-out perplexity": summary["eval_perplexity"],
            "elapsed": f"{summary['elapsed_seconds'] / 3600:.2f} h",
            "checkpoint": summary["checkpoint"],
        }
    )
    print("\nExport it so Bread and everything else can load it:")
    print(
        f"  python scripts/export_pretrained.py --run {config.output_dir} "
        f"--tokenizer {config.tokenizer_dir} --output data/models/{config.name}"
    )
    return 0


def _progress(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce a training event to the fields the API's log parser reads."""

    progress: dict[str, Any] = {"step": payload.get("step", 0)}
    for key in ("total_steps", "loss", "eval_loss"):
        if payload.get(key) is not None:
            progress[key] = payload[key]
    if payload.get("event") == "checkpoint":
        progress["checkpoint"] = payload.get("path")
    return progress


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. The last checkpoint is on disk; rerun to resume.")
        sys.exit(130)
