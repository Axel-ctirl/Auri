#!/usr/bin/env python
"""Evaluate a model or an adapter on a held-out set, and sample some answers.

    python scripts/eval_model.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
        --adapter data/runs/qlora-7b/adapter \
        --dataset data/datasets/bread_sft.eval.jsonl

Reports perplexity on the held-out records and prints a few generated answers so
you can read what actually changed.

Perplexity is a weak proxy. It tells you the model is less surprised by your
data, which is what fine-tuning optimises for; it does not tell you the answers
got better. Read the samples. Compare against the base model by running this
once with --adapter and once without.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from _bootstrap import REPO_ROOT, print_header, print_table

import sys

sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.datasets.records import read_jsonl  # noqa: E402

SAMPLE_PROMPTS = [
    "Explain what this Python function does and name one edge case it misses:\n\n"
    "def average(values):\n    return sum(values) / len(values)\n",
    "Write a Paper plugin command that teleports a player to spawn, with a "
    "permission check.",
    "This Rust code does not compile: `let s = String::from(\"hi\"); let t = s; "
    "println!(\"{}\", s);` Explain why and give the fix.",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--dataset", default=None, help="A held-out .jsonl file.")
    parser.add_argument("--max-records", type=int, default=200)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--load-in-4bit", action="store_true", default=True)
    parser.add_argument("--no-4bit", dest="load_in_4bit", action="store_false")
    args = parser.parse_args(argv)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError:
        print("error: this needs torch and transformers.")
        print("       pip install -r requirements-inference.txt")
        return 3

    print_header("Loading")
    print_table({"model": args.model_id, "adapter": args.adapter or "(none)"})

    model_kwargs = {"device_map": "auto"}
    if args.load_in_4bit:
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model_id, **model_kwargs)

    if args.adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    if args.dataset:
        dataset_path = Path(args.dataset).expanduser()
        if not dataset_path.exists():
            print(f"error: no dataset at {dataset_path}")
            return 2

        total_loss = 0.0
        total_tokens = 0
        counted = 0

        print_header("Perplexity")
        for _line_number, record, error in read_jsonl(dataset_path, limit=args.max_records):
            if error or record is None:
                continue
            messages = record.get("messages")
            if not messages:
                continue
            text = (
                tokenizer.apply_chat_template(messages, tokenize=False)
                if getattr(tokenizer, "chat_template", None)
                else "\n".join(str(message.get("content", "")) for message in messages)
            )
            encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=2048)
            encoded = {key: value.to(model.device) for key, value in encoded.items()}
            with torch.no_grad():
                outputs = model(**encoded, labels=encoded["input_ids"])
            token_count = int(encoded["input_ids"].numel())
            total_loss += float(outputs.loss) * token_count
            total_tokens += token_count
            counted += 1

        if total_tokens:
            mean_loss = total_loss / total_tokens
            print_table(
                {
                    "records": counted,
                    "tokens": f"{total_tokens:,}",
                    "mean loss": round(mean_loss, 4),
                    "perplexity": round(math.exp(mean_loss), 3),
                }
            )
        else:
            print("  no usable records found")

    print_header("Samples")
    for prompt in SAMPLE_PROMPTS:
        messages = [
            {"role": "system", "content": "You are Bread, a local coding assistant."},
            {"role": "user", "content": prompt},
        ]
        text = (
            tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            if getattr(tokenizer, "chat_template", None)
            else prompt
        )
        encoded = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=True,
                temperature=0.2,
                top_p=0.95,
                pad_token_id=tokenizer.pad_token_id,
            )
        answer = tokenizer.decode(
            generated[0][encoded["input_ids"].shape[1] :], skip_special_tokens=True
        )
        print(f"\n--- prompt ---\n{prompt.strip()}\n--- answer ---\n{answer.strip()}\n")

    print_header("Reading the result")
    print(
        "  Lower perplexity means the model finds your data less surprising.\n"
        "  It does not mean the answers are better. Compare the samples against\n"
        "  the same run without --adapter before you conclude anything."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
