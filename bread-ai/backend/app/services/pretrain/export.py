"""Export a pretrained Bread model into the format Transformers reads.

The model in ``model.py`` is deliberately laid out so that its state dict is
already what ``LlamaForCausalLM`` expects. Export is therefore a rename-free
copy plus a config file, and the result loads in Bread, vLLM, llama.cpp's
converter, or anything else that reads a Llama checkpoint.

To be clear about what this is not: sharing an architecture with Llama is not
sharing weights with it. Every tensor written here was learned from random
initialisation on your corpus.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from .model import BreadLMConfig

MODEL_CARD = """---
license: {license}
library_name: transformers
tags:
  - bread
  - pretrained-from-scratch
---

# {name}

A language model pretrained from random initialisation. No weights were
inherited from any other model.

## What this is

| | |
| --- | --- |
| Parameters | {parameters:,} |
| Non-embedding parameters | {non_embedding:,} |
| Layers | {layers} |
| Hidden size | {hidden} |
| Attention heads | {heads} ({kv_heads} key/value) |
| Context length | {context} |
| Vocabulary | {vocab:,} tokens, byte-level BPE trained on the same corpus |
| Training tokens | {tokens:,} |
| Tokens per parameter | {tokens_per_parameter} |
| Final held-out loss | {eval_loss} |
| Held-out perplexity | {eval_perplexity} |
| Trained on | {device} |
| Exported | {exported_at} |

The architecture is the conventional decoder-only stack: RMSNorm, rotary
position embeddings, grouped-query attention, SwiGLU. That matches Llama's
layout, which is why this loads in standard tooling. It does not mean any Llama
weights are present. There are none.

## What it can and cannot do

A model of this size trained on this many tokens can produce fluent text in the
domains it saw, complete short and idiomatic code, and continue a pattern it has
been shown. That is a real language model and it is entirely yours.

It cannot match a 7B model trained on trillions of tokens. It will invent APIs,
lose track of long context, and fail at multi-step reasoning. Compute and data
set that ceiling, and no amount of tuning moves it. If you need a strong coding
assistant today, use Bread's fine-tune path on an open-weight base instead, and
keep this model for the things it is genuinely good at.

Tokens per parameter is the number to watch. Below about 20 the model is
undertrained for its size, and a smaller model on the same data would have been
better.

## Use it

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("{path}")
model = AutoModelForCausalLM.from_pretrained("{path}")
```

Or in Bread:

```ini
MODEL_ID={path}
MODEL_BACKEND=transformers
QUANTIZATION_MODE=none
```

This is a base model. It completes text; it does not follow instructions. Run a
supervised fine-tune on it before expecting it to answer questions.

## Training data

{data_note}

Whoever built this model chose that corpus. Its licensing is their
responsibility, and Bread's collectors record a license for every record they
gather.
"""


def export_to_transformers(
    checkpoint_path: Path,
    tokenizer_dir: Path,
    output_dir: Path,
    *,
    model_name: str | None = None,
    license_id: str = "apache-2.0",
    data_note: str = "Collected locally with Bread's dataset tools.",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a Transformers-loadable model directory from a training checkpoint."""

    checkpoint_path = Path(checkpoint_path)
    tokenizer_dir = Path(tokenizer_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model_config = BreadLMConfig(**checkpoint["model_config"])
    state_dict: dict[str, torch.Tensor] = checkpoint["model"]

    # Drop buffers and, when embeddings are tied, the duplicate head. safetensors
    # refuses to serialise two names pointing at one storage.
    exported: dict[str, torch.Tensor] = {}
    for key, tensor in state_dict.items():
        if key.endswith("inv_freq"):
            continue
        if model_config.tie_word_embeddings and key == "lm_head.weight":
            continue
        exported[key] = tensor.detach().to(torch.float32).contiguous()

    try:
        from safetensors.torch import save_file

        save_file(exported, str(output_dir / "model.safetensors"), metadata={"format": "pt"})
    except ImportError:  # pragma: no cover - safetensors ships with transformers
        torch.save(exported, output_dir / "pytorch_model.bin")

    (output_dir / "config.json").write_text(
        json.dumps(model_config.to_hf_config(), indent=2), encoding="utf-8"
    )
    (output_dir / "generation_config.json").write_text(
        json.dumps(
            {"bos_token_id": 1, "eos_token_id": 2, "pad_token_id": 0, "do_sample": True},
            indent=2,
        ),
        encoding="utf-8",
    )

    for filename in (
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    ):
        source = tokenizer_dir / filename
        if source.exists():
            shutil.copy2(source, output_dir / filename)

    training_state = checkpoint.get("state", {})
    summary = summary or {}
    parameters = sum(tensor.numel() for tensor in exported.values())
    if model_config.tie_word_embeddings:
        parameters += 0  # the head shares storage with the embedding
    non_embedding = parameters - model_config.vocab_size * model_config.hidden_size
    tokens = int(training_state.get("tokens_seen", 0))

    card = MODEL_CARD.format(
        name=model_name or output_dir.name,
        license=license_id,
        parameters=parameters,
        non_embedding=non_embedding,
        layers=model_config.num_hidden_layers,
        hidden=model_config.hidden_size,
        heads=model_config.num_attention_heads,
        kv_heads=model_config.num_key_value_heads,
        context=model_config.max_position_embeddings,
        vocab=model_config.vocab_size,
        tokens=tokens,
        tokens_per_parameter=round(tokens / max(parameters, 1), 2),
        eval_loss=summary.get("eval_loss", training_state.get("best_eval_loss", "not measured")),
        eval_perplexity=summary.get("eval_perplexity", "not measured"),
        device=summary.get("device", "unknown"),
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
        path=output_dir.as_posix(),
        data_note=data_note,
    )
    (output_dir / "README.md").write_text(card, encoding="utf-8")

    provenance = {
        "name": model_name or output_dir.name,
        "trained_from_scratch": True,
        "base_model": None,
        "inherited_weights": "none",
        "architecture": "llama-compatible decoder-only",
        "parameters": parameters,
        "training_tokens": tokens,
        "steps": int(training_state.get("step", 0)),
        "checkpoint": str(checkpoint_path),
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (output_dir / "bread.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "parameters": parameters,
        "tensors": len(exported),
        "provenance": provenance,
    }
