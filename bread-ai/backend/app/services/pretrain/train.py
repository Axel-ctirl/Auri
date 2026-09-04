"""The pretraining loop for Bread's own models.

This is the part that makes the weights yours. It starts from random
initialisation, reads a packed corpus you built, and runs the standard
next-token objective until the loss stops falling.

Everything here is deliberately plain: one process, one device, gradient
accumulation for large effective batches, cosine decay with warmup, gradient
clipping, and checkpoints you can resume from. There is no distributed training
because there is one GPU, and adding the machinery for a second would be code
that never runs.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .data import held_out_split, iter_batches, open_shard, shard_token_count
from .model import BreadLM, BreadLMConfig, ComputeBudget


@dataclass
class PretrainConfig:
    """Everything one pretraining run needs."""

    name: str = "bread-small"
    corpus_path: str = "data/pretrain/corpus.bin"
    tokenizer_dir: str = "data/pretrain/tokenizer"
    output_dir: str = "data/runs/pretrain-bread-small"

    # Model shape.
    vocab_size: int = 32000
    hidden_size: int = 768
    intermediate_size: int = 2048
    num_hidden_layers: int = 12
    num_attention_heads: int = 12
    num_key_value_heads: int = 4
    sequence_length: int = 1024
    rope_theta: float = 10000.0
    tie_word_embeddings: bool = True

    # Schedule.
    max_steps: int = 20000
    batch_size: int = 8
    gradient_accumulation_steps: int = 8
    learning_rate: float = 3e-4
    min_learning_rate: float = 3e-5
    warmup_steps: int = 500
    weight_decay: float = 0.1
    beta1: float = 0.9
    beta2: float = 0.95
    grad_clip: float = 1.0

    # Execution.
    device: str = "auto"
    dtype: str = "bfloat16"
    compile_model: bool = False
    seed: int = 20260904
    log_every: int = 10
    eval_every: int = 500
    eval_batches: int = 20
    save_every: int = 1000
    sample_every: int = 1000
    sample_prompt: str = "def "
    sample_tokens: int = 96
    held_out_fraction: float = 0.005

    def model_config(self) -> BreadLMConfig:
        return BreadLMConfig(
            vocab_size=self.vocab_size,
            hidden_size=self.hidden_size,
            intermediate_size=self.intermediate_size,
            num_hidden_layers=self.num_hidden_layers,
            num_attention_heads=self.num_attention_heads,
            num_key_value_heads=self.num_key_value_heads,
            max_position_embeddings=self.sequence_length,
            rope_theta=self.rope_theta,
            tie_word_embeddings=self.tie_word_embeddings,
        )

    @property
    def tokens_per_step(self) -> int:
        return self.batch_size * self.gradient_accumulation_steps * self.sequence_length

    @property
    def total_tokens(self) -> int:
        return self.tokens_per_step * self.max_steps

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PretrainConfig:
        known = {key: value for key, value in payload.items() if key in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class TrainingState:
    step: int = 0
    tokens_seen: int = 0
    best_eval_loss: float = float("inf")
    history: list[dict[str, float]] = field(default_factory=list)


def resolve_device(requested: str) -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def resolve_dtype(requested: str, device: torch.device) -> torch.dtype:
    if device.type != "cuda":
        # bf16 on CPU is supported but slow and, on older CPUs, emulated.
        return torch.float32
    if requested in {"bfloat16", "bf16"}:
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    if requested in {"float16", "fp16"}:
        return torch.float16
    return torch.float32


def learning_rate_at(step: int, config: PretrainConfig) -> float:
    """Linear warmup, then cosine decay to the floor."""

    if step < config.warmup_steps:
        return config.learning_rate * (step + 1) / max(config.warmup_steps, 1)
    progress = (step - config.warmup_steps) / max(config.max_steps - config.warmup_steps, 1)
    progress = min(max(progress, 0.0), 1.0)
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))
    return config.min_learning_rate + cosine * (config.learning_rate - config.min_learning_rate)


@torch.no_grad()
def evaluate(
    model: BreadLM,
    shard: np.ndarray,
    config: PretrainConfig,
    device: torch.device,
    batches: int,
) -> float:
    model.eval()
    generator = iter_batches(
        shard,
        batch_size=config.batch_size,
        sequence_length=config.sequence_length,
        seed=config.seed + 99991,
    )
    total = 0.0
    for _ in range(batches):
        inputs, targets = next(generator)
        input_ids = torch.from_numpy(inputs).to(device)
        labels = torch.from_numpy(targets).to(device)
        # The model shifts internally, so hand it a label row aligned to inputs.
        aligned = torch.cat([input_ids[:, :1], labels[:, :-1]], dim=1)
        total += float(model(input_ids, labels=aligned)["loss"])
    model.train()
    return total / max(batches, 1)


def pretrain(
    config: PretrainConfig,
    *,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Run a pretraining job and return a summary."""

    def emit(payload: dict[str, Any]) -> None:
        if on_event is not None:
            on_event(payload)

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    device = resolve_device(config.device)
    dtype = resolve_dtype(config.dtype, device)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = Path(config.corpus_path)
    total_corpus_tokens = shard_token_count(corpus_path, config.vocab_size)
    shard = open_shard(corpus_path, config.vocab_size)
    # Evaluation needs at least a few full windows to mean anything.
    train_shard, eval_shard = held_out_split(
        shard, config.held_out_fraction, minimum_tokens=(config.sequence_length + 1) * 4
    )
    can_evaluate = eval_shard.size > config.sequence_length + 1

    model = BreadLM(config.model_config()).to(device)
    counts = model.parameter_counts()

    budget = ComputeBudget(parameters=counts["total"], tokens=config.total_tokens)
    emit(
        {
            "event": "start",
            "parameters": counts,
            "corpus_tokens": total_corpus_tokens,
            "planned_tokens": config.total_tokens,
            "tokens_per_parameter": round(config.total_tokens / max(counts["total"], 1), 2),
            "chinchilla_tokens": budget.chinchilla_tokens,
            "device": str(device),
            "dtype": str(dtype).replace("torch.", ""),
            "eval_tokens": int(eval_shard.size),
        }
    )

    if not can_evaluate:
        emit(
            {
                "event": "warning",
                "message": "The corpus is too small to hold out a usable evaluation "
                "split, so evaluation is disabled for this run. Pack more data if you "
                "want a held-out number to trust.",
            }
        )

    optimizer = model.configure_optimizer(
        config.learning_rate, config.weight_decay, (config.beta1, config.beta2)
    )
    scaler = torch.amp.GradScaler(enabled=(dtype == torch.float16))

    if config.compile_model and hasattr(torch, "compile"):
        model = torch.compile(model)  # type: ignore[assignment]

    state = TrainingState()
    checkpoint_path = output_dir / "checkpoint.pt"
    if resume and checkpoint_path.exists():
        loaded = torch.load(checkpoint_path, map_location=device, weights_only=False)
        model.load_state_dict(loaded["model"])
        optimizer.load_state_dict(loaded["optimizer"])
        state = TrainingState(**loaded["state"])
        emit({"event": "resumed", "step": state.step})

    batches = iter_batches(
        train_shard,
        batch_size=config.batch_size,
        sequence_length=config.sequence_length,
        seed=config.seed + state.step,
    )

    model.train()
    started = time.perf_counter()
    window_started = started
    window_tokens = 0

    for step in range(state.step, config.max_steps):
        current_lr = learning_rate_at(step, config)
        for group in optimizer.param_groups:
            group["lr"] = current_lr

        optimizer.zero_grad(set_to_none=True)
        accumulated_loss = 0.0

        for _ in range(config.gradient_accumulation_steps):
            inputs, targets = next(batches)
            input_ids = torch.from_numpy(inputs).to(device, non_blocking=True)
            labels = torch.from_numpy(targets).to(device, non_blocking=True)
            aligned = torch.cat([input_ids[:, :1], labels[:, :-1]], dim=1)

            with torch.autocast(
                device_type=device.type,
                dtype=dtype,
                enabled=(device.type == "cuda" and dtype != torch.float32),
            ):
                loss = model(input_ids, labels=aligned)["loss"]
                loss = loss / config.gradient_accumulation_steps

            scaler.scale(loss).backward()
            accumulated_loss += float(loss.detach()) * config.gradient_accumulation_steps

        if config.grad_clip > 0:
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)

        scaler.step(optimizer)
        scaler.update()

        state.step = step + 1
        state.tokens_seen += config.tokens_per_step
        window_tokens += config.tokens_per_step
        mean_loss = accumulated_loss / config.gradient_accumulation_steps

        if state.step % config.log_every == 0:
            now = time.perf_counter()
            tokens_per_second = window_tokens / max(now - window_started, 1e-9)
            window_started, window_tokens = now, 0
            remaining = config.max_steps - state.step
            payload = {
                "event": "step",
                "step": state.step,
                "total_steps": config.max_steps,
                "loss": round(mean_loss, 5),
                "perplexity": round(math.exp(min(mean_loss, 20)), 2),
                "learning_rate": current_lr,
                "tokens_seen": state.tokens_seen,
                "tokens_per_second": round(tokens_per_second, 1),
                "eta_hours": round(
                    remaining * config.tokens_per_step / max(tokens_per_second, 1e-9) / 3600, 2
                ),
            }
            state.history.append({"step": float(state.step), "loss": round(mean_loss, 5)})
            emit(payload)

        if can_evaluate and config.eval_every and state.step % config.eval_every == 0:
            eval_loss = evaluate(model, eval_shard, config, device, config.eval_batches)
            state.best_eval_loss = min(state.best_eval_loss, eval_loss)
            emit(
                {
                    "event": "eval",
                    "step": state.step,
                    "eval_loss": round(eval_loss, 5),
                    "eval_perplexity": round(math.exp(min(eval_loss, 20)), 2),
                    "best_eval_loss": round(state.best_eval_loss, 5),
                }
            )

        if config.save_every and state.step % config.save_every == 0:
            _save(checkpoint_path, model, optimizer, state, config)
            emit({"event": "checkpoint", "step": state.step, "path": str(checkpoint_path)})

    _save(checkpoint_path, model, optimizer, state, config)

    final_eval = (
        evaluate(model, eval_shard, config, device, config.eval_batches)
        if can_evaluate
        else float("nan")
    )
    elapsed = time.perf_counter() - started
    budget.achieved_tokens_per_second = state.tokens_seen / max(elapsed, 1e-9)

    summary = {
        "name": config.name,
        "parameters": counts,
        "steps": state.step,
        "tokens_seen": state.tokens_seen,
        "final_loss": state.history[-1]["loss"] if state.history else None,
        "eval_loss": round(final_eval, 5) if can_evaluate else None,
        "eval_perplexity": (round(math.exp(min(final_eval, 20)), 2) if can_evaluate else None),
        "elapsed_seconds": round(elapsed, 1),
        "budget": budget.summary(),
        "checkpoint": str(checkpoint_path),
        "device": str(device),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    emit({"event": "done", **summary})
    return summary


def _save(
    path: Path,
    model: BreadLM,
    optimizer: torch.optim.Optimizer,
    state: TrainingState,
    config: PretrainConfig,
) -> None:
    inner = getattr(model, "_orig_mod", model)  # unwrap torch.compile
    torch.save(
        {
            "model": inner.state_dict(),
            "optimizer": optimizer.state_dict(),
            "state": asdict(state),
            "config": config.as_dict(),
            "model_config": inner.config.as_dict(),
        },
        path,
    )
