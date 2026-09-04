#!/usr/bin/env python
"""Bake Bread's identity and voice into a standalone set of weights.

    python scripts/bake_bread_model.py --dry-run
    python scripts/bake_bread_model.py --mix data/datasets/bread_sft.jsonl

What this does, in order:

1. Builds the identity dataset from ``prompts/identity.yaml``, mixed with your
   own general coding data so the fine-tune does not narrow the model.
2. Validates it, because a malformed record fails silently during training.
3. Runs the QLoRA fine-tune from ``configs/training/bread_identity.yaml``.
4. Merges the adapter into the base weights.
5. Writes a model card and a machine-readable provenance file.

The result is a directory you can load from anything that reads Transformers
weights, hand to someone else, or convert to GGUF. It answers as Bread.

What it is honest about
-----------------------
The output is a **derivative of an open-weight base model**, not a model trained
from nothing. The generated model card says which base, under which license, and
what the fine-tune did and did not change. Do not delete those sections when you
share the weights: they are what make the claim "this is Bread" true rather than
merely asserted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = REPO_ROOT / "configs" / "training" / "bread_identity.yaml"


def load_sibling(name: str):
    """Import another script in this directory by path."""

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"bread_script_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must contain a YAML mapping.")
    return config


# --------------------------------------------------------------------- card
MODEL_CARD = """---
base_model: {base_model}
license: {base_license}
library_name: transformers
tags:
  - code
  - bread
  - qlora
---

# {model_name}

Bread is a local-first coding assistant. These are its weights.

## What this is

A fine-tune of [`{base_model}`](https://huggingface.co/{base_model}), adapted
with QLoRA on a hand-written corpus that defines Bread's identity and answering
style, mixed with general coding data. The adapter was then merged into the base
weights, so this directory is a complete model rather than a patch.

It answers as Bread: it leads with the answer, states its assumptions, says when
it is unsure rather than inventing an API, and does not claim to be a hosted
frontier assistant.

## What this is not

**It was not trained from scratch.** Pretraining a model of this class takes
thousands of accelerators running for weeks over trillions of tokens. That work
was done by the authors of `{base_model}` and released under {base_license}.
What happened here is a fine-tune on a single GPU, which shapes behaviour and
does not create capability from nothing.

**It is not equal to a hosted frontier model.** It is a {parameter_hint} open-weight
model. It is good at completing code in a familiar idiom, explaining a function,
writing tests, spotting obvious bugs and translating between languages. It is
meaningfully weaker at reasoning across many files, holding a long specification
in mind, catching subtle logic errors, and knowing recent library versions.

**It did not gain new knowledge.** Fine-tuning reliably teaches *how* to answer
and unreliably teaches *what is true*. Facts about your codebase should come
from retrieval, not from these weights.

## Training

| | |
| --- | --- |
| Base model | `{base_model}` |
| Base license | {base_license} |
| Method | QLoRA, 4-bit NF4, adapter merged into the base |
| LoRA rank / alpha | {lora_r} / {lora_alpha} |
| Target modules | {target_modules} |
| Learning rate | {learning_rate} |
| Epochs | {epochs} |
| Sequence length | {max_seq_length} |
| Training records | {record_count} |
| Identity share | {identity_share} |
| Baked on | {baked_at} |

The identity corpus lives at `prompts/identity.yaml` in the Bread repository and
is version-controlled, so what this model believes about itself is auditable.

## Data and licensing

The identity corpus is hand-written and belongs to whoever wrote it. The general
coding data was collected from local sources by the operator who baked this
model; Bread's collector records a license for every record and excludes
anything it cannot identify, but that is a heuristic filter and not a legal
clearance.

Redistributing these weights, using them commercially, and redistributing the
training data are three separate questions. `{base_license}` governs the first
two as far as the base model is concerned. Read it.

## Use it

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("{merged_dir_name}")
model = AutoModelForCausalLM.from_pretrained("{merged_dir_name}", device_map="auto")
```

Or point Bread at it:

```ini
MODEL_ID={merged_dir}
ADAPTER_PATH=
```

## Limitations and safe use

- It writes code; it does not run code. Read what it produces before you run it.
- It can produce a plausible function name that does not exist. Verify anything
  it asserts about an API you cannot see.
- Its knowledge stops at the base model's training cutoff.
- It has no safety tuning beyond what the base model carries.

Not affiliated with Anthropic, OpenAI, Mojang, Roblox, or any model provider.
"""


def parameter_hint(base_model: str) -> str:
    lowered = base_model.lower()
    for marker in ("1.5b", "3b", "7b", "14b", "32b", "70b"):
        if marker in lowered:
            return marker.upper().replace("B", "B-parameter")
    return "small"


def write_model_card(
    merged_dir: Path,
    config: dict[str, Any],
    bake: dict[str, Any],
    stats: dict[str, Any],
) -> Path:
    base_model = config.get("base_model_id", "")
    card = MODEL_CARD.format(
        model_name=bake.get("model_name", "bread-coder"),
        base_model=base_model,
        base_license=stats.get("base_license", "Apache-2.0"),
        parameter_hint=parameter_hint(base_model),
        lora_r=config.get("lora_r", ""),
        lora_alpha=config.get("lora_alpha", ""),
        target_modules=", ".join(f"`{name}`" for name in config.get("lora_target_modules", [])),
        learning_rate=config.get("learning_rate", ""),
        epochs=config.get("num_train_epochs", ""),
        max_seq_length=config.get("max_seq_length", ""),
        record_count=stats.get("record_count", "unknown"),
        identity_share=stats.get("identity_share", "unknown"),
        baked_at=stats.get("baked_at", ""),
        merged_dir=merged_dir,
        merged_dir_name=merged_dir.as_posix(),
    )
    target = merged_dir / "README.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(card, encoding="utf-8")
    return target


def write_provenance(merged_dir: Path, payload: dict[str, Any]) -> Path:
    target = merged_dir / "bread.json"
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return target


# --------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--mix",
        action="append",
        default=[],
        help="General coding dataset to mix with the identity corpus. Repeat for "
        "several. Defaults to data/datasets/bread_sft.jsonl if it exists.",
    )
    parser.add_argument("--base-model-id", default=None, help="Override the base model.")
    parser.add_argument("--output-name", default=None, help="Override the baked model name.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the dataset, run the training preflight, then stop.",
    )
    parser.add_argument("--skip-build", action="store_true", help="Reuse the existing dataset.")
    parser.add_argument("--skip-train", action="store_true", help="Reuse an existing adapter.")
    parser.add_argument("--skip-merge", action="store_true", help="Stop after training.")
    parser.add_argument(
        "--register",
        action="store_true",
        help="Add the baked model to Bread's catalogue so it appears on the Models page.",
    )
    args = parser.parse_args(argv)

    config_path = resolve(args.config)
    if not config_path.exists():
        raise SystemExit(f"error: no config at {config_path}")
    config = load_config(config_path)
    if args.base_model_id:
        config["base_model_id"] = args.base_model_id

    bake = dict(config.get("bake") or {})
    if args.output_name:
        bake["model_name"] = args.output_name
        bake["merged_dir"] = f"data/models/{args.output_name}"

    model_name = bake.get("model_name", "bread-coder")
    merged_dir = resolve(bake.get("merged_dir", f"data/models/{model_name}"))
    dataset_path = resolve(config.get("dataset_path", "data/datasets/bread_identity.jsonl"))
    run_dir = resolve(config.get("output_dir", "data/runs/bread-identity"))
    adapter_dir = run_dir / "adapter"

    mix_sources = list(args.mix)
    if not mix_sources:
        default_mix = resolve("data/datasets/bread_sft.jsonl")
        if default_mix.exists():
            mix_sources = [str(default_mix)]

    print_header(f"Baking {model_name}")
    print_table(
        {
            "config": config_path,
            "base model": config.get("base_model_id", ""),
            "identity corpus": REPO_ROOT / "prompts" / "identity.yaml",
            "general data": ", ".join(mix_sources) or "(none: see the warning below)",
            "dataset": dataset_path,
            "adapter": adapter_dir,
            "merged weights": merged_dir,
        }
    )

    if not mix_sources:
        print(
            "\n  warning: no general coding data found, so the fine-tune would see\n"
            "  identity records only. That teaches the model to introduce itself\n"
            "  and to forget how to code. Build some first:\n\n"
            "    python scripts/collect_local_code.py --path <your projects>\n"
            "    python scripts/build_sft_dataset.py \\\n"
            "        --input data/datasets/local_code.jsonl \\\n"
            "        --output data/datasets/bread_sft.jsonl\n"
        )

    # ------------------------------------------------------------ 1. dataset
    identity_share = "unknown"
    record_count = "unknown"

    if args.skip_build:
        print("\nStep 1/4: reusing the existing dataset.")
        if not dataset_path.exists():
            raise SystemExit(f"error: --skip-build was given but {dataset_path} is missing.")
    else:
        print("\nStep 1/4: building the identity dataset.\n")
        builder = load_sibling("build_identity_dataset")
        build_argv = [
            "--output",
            str(dataset_path),
            "--mix-ratio",
            str(bake.get("mix_ratio", 8)),
            "--repeat",
            str(bake.get("identity_repeat", 2)),
        ]
        if config.get("base_model_id"):
            build_argv += ["--base-model", str(config["base_model_id"])]
        for source in mix_sources:
            build_argv += ["--mix", source]

        exit_code = builder.main(build_argv)
        if exit_code != 0:
            return exit_code

    # ------------------------------------------------------------ 2. validate
    print("\nStep 2/4: validating the dataset.\n")
    validator = load_sibling("validate_dataset")
    # Identity records repeat on purpose, so duplicates are expected here; the
    # validator reports them without failing, and invalid records do fail.
    if validator.main(["--input", str(dataset_path), "--schema", "sft_chat"]) != 0:
        print("\nerror: the dataset did not validate. Fix it before training.", file=sys.stderr)
        return 1

    from app.services.datasets.quality import build_report

    report = build_report(dataset_path)
    record_count = report["total_records"]
    identity_records = sum(
        count
        for source, count in report["source_counts"].items()
        if source.startswith("bread_identity/")
    )
    if record_count:
        identity_share = f"{identity_records / record_count * 100:.1f}%"

    print_table({"records": record_count, "identity share": identity_share})

    if record_count and identity_records / record_count > 0.30:
        print(
            "\n  warning: identity records are "
            f"{identity_share} of this dataset. Above roughly 30% the model\n"
            "  starts over-indexing on talking about itself, and its coding\n"
            "  ability measurably degrades. Collect more general data before you\n"
            "  bake anything you intend to keep:\n\n"
            "    python scripts/collect_local_code.py --path <your projects>\n"
            "    python scripts/build_sft_dataset.py \\\n"
            "        --input data/datasets/local_code.jsonl \\\n"
            "        --output data/datasets/bread_sft.jsonl\n"
        )

    # ------------------------------------------------------------ 3. training
    trainer = load_sibling("train_qlora")
    train_argv = [
        "--config",
        str(config_path),
        "--dataset",
        str(dataset_path),
        "--output-dir",
        str(run_dir),
    ]
    if args.base_model_id:
        train_argv += ["--base-model-id", args.base_model_id]

    if args.dry_run:
        print("\nStep 3/4: training preflight (dry run).\n")
        try:
            trainer.main([*train_argv, "--dry-run"])
        except SystemExit as exc:
            print(f"\npreflight stopped: {exc}", file=sys.stderr)
            return 2
        print("\nDry run complete. Nothing was trained and no weights were written.")
        print("Re-run without --dry-run to bake the model.")
        return 0

    if args.skip_train:
        print("\nStep 3/4: reusing the existing adapter.")
        if not (adapter_dir / "adapter_config.json").exists():
            raise SystemExit(f"error: --skip-train was given but {adapter_dir} has no adapter.")
    else:
        print("\nStep 3/4: training. This is the long part.\n")
        try:
            exit_code = trainer.main(train_argv)
        except SystemExit as exc:
            print(f"\ntraining stopped: {exc}", file=sys.stderr)
            return 3
        if exit_code != 0:
            return exit_code

    if args.skip_merge:
        print(f"\nStopping before the merge. The adapter is at {adapter_dir}.")
        return 0

    # ------------------------------------------------------------ 4. merge
    print("\nStep 4/4: merging the adapter into standalone weights.\n")
    merger = load_sibling("merge_lora")
    merge_argv = [
        "--base-model-id",
        str(config.get("base_model_id", "")),
        "--adapter",
        str(adapter_dir),
        "--output",
        str(merged_dir),
        "--dtype",
        str(bake.get("merge_dtype", "bfloat16")),
        "--device",
        str(bake.get("merge_device", "cpu")),
    ]
    exit_code = merger.main(merge_argv)
    if exit_code != 0:
        return exit_code

    # ------------------------------------------------------------ card
    identity_corpus = yaml.safe_load(
        (REPO_ROOT / "prompts" / "identity.yaml").read_text(encoding="utf-8")
    )
    baked_at = datetime.now(UTC).isoformat(timespec="seconds")
    stats = {
        "base_license": identity_corpus.get("base_license", "Apache-2.0"),
        "record_count": record_count,
        "identity_share": identity_share,
        "baked_at": baked_at,
    }

    card_path = write_model_card(merged_dir, config, bake, stats)
    provenance_path = write_provenance(
        merged_dir,
        {
            "name": model_name,
            "base_model": config.get("base_model_id"),
            "base_license": stats["base_license"],
            "method": "qlora-merged",
            "trained_from_scratch": False,
            "identity_corpus": "prompts/identity.yaml",
            "identity_corpus_version": identity_corpus.get("version"),
            "training_config": str(config_path.relative_to(REPO_ROOT)),
            "dataset": str(dataset_path),
            "record_count": record_count,
            "identity_share": identity_share,
            "lora": {
                "r": config.get("lora_r"),
                "alpha": config.get("lora_alpha"),
                "target_modules": config.get("lora_target_modules"),
            },
            "baked_at": baked_at,
        },
    )

    if args.register:
        _register(model_name, merged_dir, config)

    print_header("Done")
    print_table(
        {
            "weights": merged_dir,
            "model card": card_path,
            "provenance": provenance_path,
        }
    )
    print("\nUse it by putting this in .env and reloading the model:")
    print(f"  MODEL_ID={merged_dir}")
    print("  ADAPTER_PATH=")
    print("\nOr check it answers as itself before you commit to it:")
    print(f"  python scripts/eval_model.py --model-id {merged_dir} --no-4bit")
    print(
        "\nKeep the 'What this is not' section of the model card if you share these\n"
        "weights. It is what makes the claim honest."
    )
    return 0


def _register(model_name: str, merged_dir: Path, config: dict[str, Any]) -> None:
    """Add the baked model to Bread's catalogue."""

    from sqlmodel import select

    from app.db import init_db, new_session
    from app.models import ModelRecord

    init_db()
    with new_session() as session:
        existing = session.exec(
            select(ModelRecord).where(ModelRecord.model_id == str(merged_dir))
        ).first()
        if existing is not None:
            print(f"  catalogue: '{existing.name}' already points at these weights")
            return
        session.add(
            ModelRecord(
                name=model_name,
                model_id=str(merged_dir),
                backend="transformers",
                quantization_mode="4bit",
                dtype=str(config.get("bnb_4bit_compute_dtype", "bfloat16")),
                context_length=int(config.get("max_seq_length", 2048)) * 4,
                notes=f"Baked locally from {config.get('base_model_id')} with "
                "scripts/bake_bread_model.py. Answers as Bread.",
                is_builtin=False,
            )
        )
        session.commit()
    print(f"  catalogue: registered '{model_name}'")


if __name__ == "__main__":
    raise SystemExit(main())
