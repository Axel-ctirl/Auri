#!/usr/bin/env python
"""Merge a LoRA adapter into its base model and save standalone weights.

    python scripts/merge_lora.py \
        --base-model-id Qwen/Qwen2.5-Coder-7B-Instruct \
        --adapter data/runs/qlora-7b/adapter \
        --output data/runs/qlora-7b/merged

When to merge, and when not to
------------------------------
Merging removes the adapter indirection, which makes the model marginally faster
and lets you convert it to GGUF. It also produces a full-size copy of the model
on disk: about 15 GB for a 7B.

Do not merge if you want to keep swapping adapters, or if disk is tight. Bread
loads an adapter at runtime through ADAPTER_PATH with no merge step.

Merging happens in fp16 or bf16, never in 4-bit. Merging into a quantized model
loses the precision the adapter was trained against, so this needs enough RAM or
VRAM to hold the full-precision base.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header, print_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-model-id", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32"])
    parser.add_argument("--device", default="cpu", help="'cpu' is slower but needs no VRAM.")
    args = parser.parse_args(argv)

    adapter_path = Path(args.adapter).expanduser()
    if not (adapter_path / "adapter_config.json").exists():
        print(f"error: {adapter_path} does not look like an adapter directory.")
        print("       It should contain adapter_config.json.")
        return 2

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        print("error: this needs torch, transformers and peft.")
        print("       pip install -r requirements-inference.txt")
        return 3

    output_path = Path(args.output).expanduser()
    print_header("Merging adapter into base weights")
    print_table(
        {
            "base model": args.base_model_id,
            "adapter": adapter_path,
            "output": output_path,
            "dtype": args.dtype,
            "device": args.device,
        }
    )
    print("\nLoading the base model at full precision. This needs the memory the")
    print("4-bit training run did not.\n")

    base = AutoModelForCausalLM.from_pretrained(
        args.base_model_id,
        torch_dtype=getattr(torch, args.dtype),
        device_map=args.device,
    )
    merged = PeftModel.from_pretrained(base, str(adapter_path)).merge_and_unload()

    output_path.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(output_path), safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base_model_id).save_pretrained(str(output_path))

    print_header("Done")
    print_table({"merged weights": output_path})
    print("\nPoint Bread at it with MODEL_ID=" + str(output_path) + " and an empty")
    print("ADAPTER_PATH.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
