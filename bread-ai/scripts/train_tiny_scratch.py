#!/usr/bin/env python
"""Train a tiny character-level transformer from scratch. THIS IS A TOY.

    python scripts/train_tiny_scratch.py --config configs/training/tiny_scratch.yaml

Read this first
---------------
This trains a few-million-parameter model on a few megabytes of your own plain
English. It exists so the mechanics of pretraining are concrete rather than
abstract: a vocabulary, batched context windows, a loss that falls, and samples
that go from noise to something that looks like words.

It will not produce a useful assistant. It will not write working code. It is
not a small Claude or a small anything, and no amount of tuning on one GPU makes
it one. The gap between this and a frontier model is roughly six orders of
magnitude in both compute and data, and that gap is not closeable at home.

For a model that actually helps you write code, fine-tune an open-weight model:

    python scripts/train_qlora.py --config configs/training/qlora_7b.yaml

Expected outcome here: after a few thousand steps on a few megabytes of English,
the model produces text with plausible word shapes, occasional real words, and
no coherent meaning. That is success for this script.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import yaml

from _bootstrap import REPO_ROOT, print_header, print_table


def emit(payload: dict[str, Any]) -> None:
    print("BREAD_PROGRESS " + json.dumps(payload), flush=True)


def resolve(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


def load_corpus(dataset_path: Path) -> str:
    """Read plain text out of a JSONL dataset, or a .txt file directly."""

    if dataset_path.suffix == ".txt":
        return dataset_path.read_text(encoding="utf-8", errors="ignore")

    import sys

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.services.datasets.records import read_jsonl, record_text

    pieces: list[str] = []
    for _line_number, record, error in read_jsonl(dataset_path):
        if error or record is None:
            continue
        pieces.append(record_text(record))
    return "\n\n".join(pieces)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--run-id", default=None, help="Set by the API; ignored otherwise.")
    parser.add_argument("--max-steps", type=int, default=None)
    args = parser.parse_args(argv)

    config_path = resolve(args.config)
    if not config_path.exists():
        raise SystemExit(f"error: no config at {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    dataset_path = resolve(args.dataset or config.get("dataset_path", ""))
    output_dir = resolve(args.output_dir or config.get("output_dir", "data/runs/tiny-scratch"))
    max_steps = args.max_steps or int(config.get("max_steps", 3000))

    print_header("Tiny from-scratch transformer (educational)")
    print(
        "  This is a demonstration of pretraining mechanics, not a useful model.\n"
        "  For an assistant that can help you, use scripts/train_qlora.py.\n"
    )

    if not dataset_path.exists():
        raise SystemExit(
            f"error: no dataset at {dataset_path}.\n"
            "       Collect some of your own English first:\n"
            "         python scripts/collect_english.py --path ~/Documents/notes"
        )

    try:
        import torch
        import torch.nn as nn
        from torch.nn import functional as F
    except ImportError:
        raise SystemExit("error: PyTorch is not installed. See docs/WINDOWS_SETUP.md.") from None

    torch.manual_seed(int(config.get("seed", 20260903)))
    device = "cuda" if torch.cuda.is_available() else "cpu"

    text = load_corpus(dataset_path)
    if len(text) < 10_000:
        print(
            f"warning: only {len(text)} characters of training text. Below roughly "
            "one megabyte the model memorises rather than learns anything.\n"
        )

    vocabulary = sorted(set(text))
    stoi = {character: index for index, character in enumerate(vocabulary)}
    itos = dict(enumerate(vocabulary))
    data = torch.tensor([stoi[character] for character in text], dtype=torch.long)

    split_at = int(len(data) * 0.9)
    train_data, val_data = data[:split_at], data[split_at:]

    block_size = int(config.get("block_size", 256))
    batch_size = int(config.get("batch_size", 32))
    n_embd = int(config.get("n_embd", 384))
    n_head = int(config.get("n_head", 6))
    n_layer = int(config.get("n_layer", 6))
    dropout = float(config.get("dropout", 0.2))

    print_table(
        {
            "corpus characters": f"{len(text):,}",
            "vocabulary size": len(vocabulary),
            "device": device,
            "layers": n_layer,
            "heads": n_head,
            "embedding": n_embd,
            "context": block_size,
            "steps": max_steps,
        }
    )

    def get_batch(split: str):
        source = train_data if split == "train" else val_data
        if len(source) <= block_size + 1:
            raise SystemExit("error: the corpus is smaller than one context window.")
        starts = torch.randint(len(source) - block_size - 1, (batch_size,))
        inputs = torch.stack([source[start : start + block_size] for start in starts])
        targets = torch.stack([source[start + 1 : start + block_size + 1] for start in starts])
        return inputs.to(device), targets.to(device)

    class CausalSelfAttention(nn.Module):
        """Multi-head attention with a causal mask, written out for clarity."""

        def __init__(self) -> None:
            super().__init__()
            self.attention = nn.Linear(n_embd, 3 * n_embd, bias=False)
            self.projection = nn.Linear(n_embd, n_embd, bias=False)
            self.attention_dropout = nn.Dropout(dropout)
            self.residual_dropout = nn.Dropout(dropout)
            self.register_buffer(
                "causal_mask",
                torch.tril(torch.ones(block_size, block_size)).view(1, 1, block_size, block_size),
            )

        def forward(self, x):
            batch, time_steps, channels = x.shape
            queries, keys, values = self.attention(x).split(n_embd, dim=2)
            head_dim = channels // n_head
            queries = queries.view(batch, time_steps, n_head, head_dim).transpose(1, 2)
            keys = keys.view(batch, time_steps, n_head, head_dim).transpose(1, 2)
            values = values.view(batch, time_steps, n_head, head_dim).transpose(1, 2)

            scores = (queries @ keys.transpose(-2, -1)) / math.sqrt(head_dim)
            scores = scores.masked_fill(
                self.causal_mask[:, :, :time_steps, :time_steps] == 0, float("-inf")
            )
            weights = self.attention_dropout(F.softmax(scores, dim=-1))
            out = (weights @ values).transpose(1, 2).contiguous().view(batch, time_steps, channels)
            return self.residual_dropout(self.projection(out))

    class Block(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.attention_norm = nn.LayerNorm(n_embd)
            self.attention = CausalSelfAttention()
            self.feedforward_norm = nn.LayerNorm(n_embd)
            self.feedforward = nn.Sequential(
                nn.Linear(n_embd, 4 * n_embd),
                nn.GELU(),
                nn.Linear(4 * n_embd, n_embd),
                nn.Dropout(dropout),
            )

        def forward(self, x):
            x = x + self.attention(self.attention_norm(x))
            return x + self.feedforward(self.feedforward_norm(x))

    class TinyTransformer(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.token_embedding = nn.Embedding(len(vocabulary), n_embd)
            self.position_embedding = nn.Embedding(block_size, n_embd)
            self.blocks = nn.Sequential(*[Block() for _ in range(n_layer)])
            self.final_norm = nn.LayerNorm(n_embd)
            self.head = nn.Linear(n_embd, len(vocabulary), bias=False)

        def forward(self, indices, targets=None):
            _batch, time_steps = indices.shape
            positions = torch.arange(time_steps, device=indices.device)
            x = self.token_embedding(indices) + self.position_embedding(positions)
            x = self.final_norm(self.blocks(x))
            logits = self.head(x)

            if targets is None:
                return logits, None
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.reshape(-1))
            return logits, loss

        @torch.no_grad()
        def generate(self, indices, max_new_tokens: int, temperature: float = 0.8):
            for _ in range(max_new_tokens):
                cropped = indices[:, -block_size:]
                logits, _ = self(cropped)
                logits = logits[:, -1, :] / max(temperature, 1e-5)
                probabilities = F.softmax(logits, dim=-1)
                next_index = torch.multinomial(probabilities, num_samples=1)
                indices = torch.cat((indices, next_index), dim=1)
            return indices

    model = TinyTransformer().to(device)
    parameter_count = sum(p.numel() for p in model.parameters())
    print_table({"parameters": f"{parameter_count:,}"})
    print(
        f"\n  For scale: this model has {parameter_count / 1e6:.1f}M parameters. "
        "A small\n  open-weight coding model has 1,500M, and a frontier model has "
        "several\n  hundred thousand million. The difference is not a tuning "
        "problem.\n"
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config.get("learning_rate", 3e-4)),
        weight_decay=float(config.get("weight_decay", 0.1)),
    )

    eval_interval = int(config.get("eval_interval", 250))
    eval_iters = int(config.get("eval_iters", 50))
    grad_clip = float(config.get("grad_clip", 1.0))

    @torch.no_grad()
    def estimate_loss() -> dict[str, float]:
        model.eval()
        losses = {}
        for split in ("train", "val"):
            values = torch.zeros(eval_iters)
            for index in range(eval_iters):
                inputs, targets = get_batch(split)
                _logits, loss = model(inputs, targets)
                values[index] = loss.item()
            losses[split] = float(values.mean())
        model.train()
        return losses

    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    emit({"step": 0, "total_steps": max_steps, "status": "started"})

    for step in range(1, max_steps + 1):
        inputs, targets = get_batch("train")
        _logits, loss = model(inputs, targets)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()

        if step % eval_interval == 0 or step == max_steps:
            losses = estimate_loss()
            elapsed = time.perf_counter() - started
            print(
                f"  step {step:>6}/{max_steps}  train {losses['train']:.4f}  "
                f"val {losses['val']:.4f}  {elapsed:.0f}s"
            )
            emit(
                {
                    "step": step,
                    "total_steps": max_steps,
                    "loss": round(losses["train"], 5),
                    "eval_loss": round(losses["val"], 5),
                }
            )
        elif step % 25 == 0:
            emit({"step": step, "total_steps": max_steps, "loss": round(loss.item(), 5)})

    checkpoint_path = output_dir / "tiny_model.pt"
    torch.save(
        {
            "model_state": model.state_dict(),
            "stoi": stoi,
            "itos": itos,
            "config": {
                "block_size": block_size,
                "n_embd": n_embd,
                "n_head": n_head,
                "n_layer": n_layer,
            },
        },
        checkpoint_path,
    )
    emit({"step": max_steps, "status": "completed", "checkpoint": str(checkpoint_path)})

    prompt = str(config.get("sample_prompt", "The"))
    context = torch.tensor(
        [[stoi.get(character, 0) for character in prompt]],
        dtype=torch.long,
        device=device,
    )
    sample = model.generate(context, int(config.get("sample_tokens", 200)))[0].tolist()

    print_header("Sample")
    print("".join(itos[index] for index in sample))
    print_header("Done")
    print_table({"checkpoint": checkpoint_path, "parameters": f"{parameter_count:,}"})
    print(
        "\n  If that sample looks like nonsense with the shape of English, the run\n"
        "  worked. That is the ceiling for a model this size on data this small.\n"
        "  Use scripts/train_qlora.py for a model that can actually help you."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
