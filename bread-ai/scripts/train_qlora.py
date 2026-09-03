#!/usr/bin/env python
"""Fine-tune an open-weight coding model with LoRA or QLoRA.

    python scripts/train_qlora.py --config configs/training/qlora_7b.yaml
    python scripts/train_qlora.py --config configs/training/qlora_7b.yaml \
        --dataset data/datasets/bread_sft.jsonl --output-dir data/runs/my-run

What this does
--------------
It freezes an existing pretrained model, quantizes it to 4-bit to fit in VRAM,
and trains a small set of low-rank adapter matrices on top. The result is an
adapter directory of a few dozen megabytes that you point Bread at with
ADAPTER_PATH.

What this does not do
---------------------
It does not train a model from scratch, and no single consumer GPU can. A
frontier model is trained on thousands of accelerators for weeks over trillions
of tokens. Fine-tuning adapts what a model already knows to your style, your
codebase and your task mix. That is a real and useful gain, and it is a
different thing from pretraining. See docs/LIMITATIONS.md.

Progress
--------
The script prints ``BREAD_PROGRESS {...}`` lines. The API reads them to update
the Training page; they are also readable on their own in a terminal.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must contain a YAML mapping.")
    return config


def emit(payload: dict[str, Any]) -> None:
    """Print a machine-readable progress line the API can parse."""

    print("BREAD_PROGRESS " + json.dumps(payload), flush=True)


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def require(package: str, install_hint: str) -> None:
    try:
        __import__(package)
    except ImportError:
        raise SystemExit(
            f"error: '{package}' is not installed.\n       {install_hint}"
        ) from None


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", default=None, help="Override dataset_path.")
    parser.add_argument("--output-dir", default=None, help="Override output_dir.")
    parser.add_argument("--base-model-id", default=None, help="Override base_model_id.")
    parser.add_argument("--run-id", default=None, help="Set by the API; ignored otherwise.")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the config, dataset and GPU, then exit without training.",
    )
    return parser


def format_examples(dataset, tokenizer, config: dict[str, Any]):
    """Render each record into a single training string using the chat template."""

    system_fallback = config.get(
        "default_system_prompt",
        "You are Bread, a local coding assistant. Answer accurately and say when "
        "you are unsure.",
    )

    def render(record: dict[str, Any]) -> dict[str, str]:
        messages = record.get("messages")
        if not messages:
            instruction = record.get("instruction") or ""
            extra = record.get("input") or ""
            user = f"{instruction}\n\n{extra}".strip() if extra else instruction
            messages = [
                {"role": "system", "content": system_fallback},
                {"role": "user", "content": user},
                {"role": "assistant", "content": record.get("output") or record.get("text", "")},
            ]
        if messages and messages[0].get("role") != "system":
            messages = [{"role": "system", "content": system_fallback}, *messages]

        if getattr(tokenizer, "chat_template", None):
            text = tokenizer.apply_chat_template(messages, tokenize=False)
        else:
            text = "\n\n".join(
                f"### {message['role'].capitalize()}\n{message['content']}"
                for message in messages
            )
        return {"text": text}

    return dataset.map(render, remove_columns=dataset.column_names)


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)

    config_path = resolve(args.config)
    if not config_path.exists():
        raise SystemExit(f"error: no config at {config_path}")
    config = load_config(config_path)

    base_model_id = args.base_model_id or config.get("base_model_id")
    dataset_path = resolve(args.dataset or config.get("dataset_path", ""))
    output_dir = resolve(args.output_dir or config.get("output_dir", "data/runs/qlora"))
    max_steps = args.max_steps if args.max_steps is not None else int(config.get("max_steps", -1))

    print_header("Bread fine-tuning run")
    print_table(
        {
            "config": config_path,
            "base model": base_model_id,
            "dataset": dataset_path,
            "output": output_dir,
            "method": config.get("method", "qlora"),
            "4-bit": config.get("load_in_4bit", True),
            "LoRA rank": config.get("lora_r", 32),
            "sequence length": config.get("max_seq_length", 2048),
        }
    )

    if not base_model_id:
        raise SystemExit("error: the config has no base_model_id.")
    if not dataset_path.exists():
        raise SystemExit(
            f"error: no dataset at {dataset_path}.\n"
            "       Build one with scripts/collect_local_code.py and "
            "scripts/build_sft_dataset.py."
        )

    require("torch", "Install the CUDA build first: see docs/WINDOWS_SETUP.md")
    require("transformers", "pip install -r requirements-train.txt")
    require("peft", "pip install -r requirements-train.txt")
    require("trl", "pip install -r requirements-train.txt")
    require("datasets", "pip install -r requirements-train.txt")

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainerCallback,
    )

    if not torch.cuda.is_available():
        print(
            "\nwarning: no CUDA device is visible. Training on CPU is possible in "
            "principle and impractical in fact: expect days per epoch. Stop here "
            "unless you know that is what you want.\n"
        )
    else:
        properties = torch.cuda.get_device_properties(0)
        total_gb = properties.total_memory / (1024**3)
        print_table(
            {
                "gpu": properties.name,
                "vram": f"{total_gb:.1f} GB",
                "capability": f"{properties.major}.{properties.minor}",
            }
        )
        required = float(config.get("min_vram_gb", 0) or 0)
        if required and total_gb + 0.5 < required:
            print(
                f"\nwarning: this config expects about {required:.0f} GB and the "
                f"card reports {total_gb:.1f} GB. Use "
                "configs/training/lora_small_fallback.yaml, or lower "
                "max_seq_length and lora_r.\n"
            )

    raw_dataset = load_dataset("json", data_files=str(dataset_path), split="train")
    eval_path = dataset_path.with_name(dataset_path.stem + ".eval.jsonl")
    raw_eval = (
        load_dataset("json", data_files=str(eval_path), split="train")
        if eval_path.exists()
        else None
    )
    print_table(
        {
            "train records": len(raw_dataset),
            "eval records": len(raw_eval) if raw_eval is not None else 0,
        }
    )

    if args.dry_run:
        print("\nDry run complete. Nothing was trained.")
        return 0

    tokenizer_id = config.get("tokenizer_id") or base_model_id
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_id, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    train_dataset = format_examples(raw_dataset, tokenizer, config)
    eval_dataset = format_examples(raw_eval, tokenizer, config) if raw_eval is not None else None

    compute_dtype = getattr(torch, str(config.get("bnb_4bit_compute_dtype", "bfloat16")))
    model_kwargs: dict[str, Any] = {"device_map": "auto", "trust_remote_code": False}

    if config.get("load_in_4bit", True):
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=str(config.get("bnb_4bit_quant_type", "nf4")),
            bnb_4bit_use_double_quant=bool(config.get("bnb_4bit_use_double_quant", True)),
            bnb_4bit_compute_dtype=compute_dtype,
        )
    else:
        model_kwargs["torch_dtype"] = compute_dtype

    print("\nLoading the base model. The first run downloads weights if they are")
    print("not cached yet; that is the slow part.\n")
    model = AutoModelForCausalLM.from_pretrained(base_model_id, **model_kwargs)
    model.config.use_cache = False

    if config.get("load_in_4bit", True):
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=bool(config.get("gradient_checkpointing", True))
        )

    lora_config = LoraConfig(
        r=int(config.get("lora_r", 32)),
        lora_alpha=int(config.get("lora_alpha", 64)),
        lora_dropout=float(config.get("lora_dropout", 0.05)),
        bias=str(config.get("lora_bias", "none")),
        task_type="CAUSAL_LM",
        target_modules=list(config.get("lora_target_modules", ["q_proj", "v_proj"])),
    )
    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print_table(
        {
            "trainable parameters": f"{trainable:,}",
            "total parameters": f"{total:,}",
            "trainable share": f"{100 * trainable / max(total, 1):.3f}%",
        }
    )

    class ProgressReporter(TrainerCallback):
        """Turns Trainer log events into BREAD_PROGRESS lines."""

        def on_log(self, trainer_args, state, control, logs=None, **kwargs):
            if not logs:
                return
            payload: dict[str, Any] = {"step": int(state.global_step)}
            if state.max_steps:
                payload["total_steps"] = int(state.max_steps)
            if "loss" in logs:
                payload["loss"] = round(float(logs["loss"]), 5)
            if "eval_loss" in logs:
                payload["eval_loss"] = round(float(logs["eval_loss"]), 5)
            if "learning_rate" in logs:
                payload["learning_rate"] = float(logs["learning_rate"])
            emit(payload)

        def on_save(self, trainer_args, state, control, **kwargs):
            emit(
                {
                    "step": int(state.global_step),
                    "checkpoint": str(
                        Path(trainer_args.output_dir) / f"checkpoint-{state.global_step}"
                    ),
                }
            )

    trainer = build_trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        config=config,
        output_dir=output_dir,
        max_steps=max_steps,
        callbacks=[ProgressReporter()],
    )

    print("\nTraining. Watch VRAM with nvidia-smi; if it climbs to the limit and")
    print("stalls, lower max_seq_length before anything else.\n")
    emit({"step": 0, "status": "started"})

    result = trainer.train()

    adapter_dir = output_dir / "adapter"
    trainer.model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    metrics = dict(result.metrics or {})
    final_loss = metrics.get("train_loss")
    emit(
        {
            "step": int(trainer.state.global_step),
            "loss": round(float(final_loss), 5) if final_loss is not None else None,
            "status": "completed",
            "checkpoint": str(adapter_dir),
        }
    )

    print_header("Done")
    print_table(
        {
            "adapter": adapter_dir,
            "steps": trainer.state.global_step,
            "final train loss": round(float(final_loss), 4) if final_loss is not None else "n/a",
            "perplexity": (
                round(math.exp(float(final_loss)), 2)
                if final_loss is not None and float(final_loss) < 20
                else "n/a"
            ),
        }
    )
    print("\nUse it by setting these in .env, then reloading the model in Bread:")
    print(f"  MODEL_ID={base_model_id}")
    print(f"  ADAPTER_PATH={adapter_dir}")
    print("\nOr merge it into standalone weights:")
    print(
        f"  python scripts/merge_lora.py --base-model-id {base_model_id} "
        f"--adapter {adapter_dir} --output {output_dir / 'merged'}"
    )
    return 0


def build_trainer(
    *,
    model,
    tokenizer,
    train_dataset,
    eval_dataset,
    config: dict[str, Any],
    output_dir: Path,
    max_steps: int,
    callbacks: list,
):
    """Construct a TRL SFTTrainer across the API shapes TRL has shipped.

    TRL moved its training arguments into ``SFTConfig`` and later moved
    ``max_seq_length`` and ``packing`` onto it as well. Rather than pin one
    version, try the current shape and fall back.
    """

    from trl import SFTTrainer

    common = {
        "output_dir": str(output_dir),
        "num_train_epochs": float(config.get("num_train_epochs", 2)),
        "max_steps": int(max_steps),
        "per_device_train_batch_size": int(config.get("per_device_train_batch_size", 1)),
        "gradient_accumulation_steps": int(config.get("gradient_accumulation_steps", 16)),
        "learning_rate": float(config.get("learning_rate", 2e-4)),
        "lr_scheduler_type": str(config.get("lr_scheduler_type", "cosine")),
        "warmup_ratio": float(config.get("warmup_ratio", 0.03)),
        "weight_decay": float(config.get("weight_decay", 0.0)),
        "max_grad_norm": float(config.get("max_grad_norm", 0.3)),
        "optim": str(config.get("optim", "paged_adamw_8bit")),
        "bf16": bool(config.get("bf16", True)),
        "fp16": bool(config.get("fp16", False)),
        "gradient_checkpointing": bool(config.get("gradient_checkpointing", True)),
        "group_by_length": bool(config.get("group_by_length", True)),
        "logging_steps": int(config.get("logging_steps", 5)),
        "save_steps": int(config.get("save_steps", 200)),
        "save_total_limit": int(config.get("save_total_limit", 3)),
        "seed": int(config.get("seed", 20260903)),
        "report_to": str(config.get("report_to", "none")),
    }
    if eval_dataset is not None:
        common["eval_steps"] = int(config.get("eval_steps", 200))

    max_seq_length = int(config.get("max_seq_length", 2048))
    packing = bool(config.get("packing", False))

    try:
        from trl import SFTConfig

        try:
            training_args = SFTConfig(
                **common,
                max_seq_length=max_seq_length,
                packing=packing,
                dataset_text_field="text",
            )
            return SFTTrainer(
                model=model,
                args=training_args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                callbacks=callbacks,
            )
        except TypeError:
            # Older SFTConfig without the dataset/packing fields.
            training_args = SFTConfig(**common)
            return SFTTrainer(
                model=model,
                args=training_args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                dataset_text_field="text",
                max_seq_length=max_seq_length,
                packing=packing,
                tokenizer=tokenizer,
                callbacks=callbacks,
            )
    except ImportError:
        from transformers import TrainingArguments

        training_args = TrainingArguments(**common)
        return SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            packing=packing,
            tokenizer=tokenizer,
            callbacks=callbacks,
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Any checkpoint already written is still on disk.")
        sys.exit(130)
