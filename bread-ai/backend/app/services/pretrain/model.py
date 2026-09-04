"""Bread's own language model, trained from random initialisation.

There is no Qwen here and nothing inherited. Every weight in a model built from
this file starts as noise and learns from data you chose.

The architecture is the modern decoder-only stack: RMSNorm, rotary position
embeddings, grouped-query attention and a SwiGLU feed-forward block. That is the
same shape Llama uses, and the module names and tensor layout match it exactly.
The reason is practical rather than aesthetic: it means ``export_pretrained.py``
can write a checkpoint that ``transformers`` loads with no custom code, so a
model you pretrained here works in Bread, in vLLM, or anywhere else, on day one.

Matching a public architecture is not the same as starting from public weights.
The shape of the building is conventional. The bricks are yours.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor, nn


@dataclass
class BreadLMConfig:
    """Shape of the model. Field names mirror ``transformers`` LlamaConfig."""

    vocab_size: int = 32000
    hidden_size: int = 768
    intermediate_size: int = 2048
    num_hidden_layers: int = 12
    num_attention_heads: int = 12
    num_key_value_heads: int = 4
    max_position_embeddings: int = 1024
    rms_norm_eps: float = 1e-5
    rope_theta: float = 10000.0
    # Tying saves a vocab-sized matrix, which is a large share of a small model.
    tie_word_embeddings: bool = True
    attention_dropout: float = 0.0
    initializer_range: float = 0.02

    @property
    def head_dim(self) -> int:
        if self.hidden_size % self.num_attention_heads != 0:
            raise ValueError("hidden_size must divide evenly by num_attention_heads")
        return self.hidden_size // self.num_attention_heads

    def __post_init__(self) -> None:
        if self.num_attention_heads % self.num_key_value_heads != 0:
            raise ValueError("num_attention_heads must be a multiple of num_key_value_heads")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_hf_config(self) -> dict[str, Any]:
        """A config.json that ``LlamaForCausalLM`` accepts verbatim."""

        return {
            "architectures": ["LlamaForCausalLM"],
            "model_type": "llama",
            "vocab_size": self.vocab_size,
            "hidden_size": self.hidden_size,
            "intermediate_size": self.intermediate_size,
            "num_hidden_layers": self.num_hidden_layers,
            "num_attention_heads": self.num_attention_heads,
            "num_key_value_heads": self.num_key_value_heads,
            "max_position_embeddings": self.max_position_embeddings,
            "rms_norm_eps": self.rms_norm_eps,
            "rope_theta": self.rope_theta,
            "tie_word_embeddings": self.tie_word_embeddings,
            "hidden_act": "silu",
            "attention_bias": False,
            "mlp_bias": False,
            "torch_dtype": "float32",
            "bos_token_id": 1,
            "eos_token_id": 2,
            "pad_token_id": 0,
        }


class RMSNorm(nn.Module):
    """Root-mean-square layer norm. No mean subtraction, no bias."""

    def __init__(self, hidden_size: int, eps: float = 1e-5) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(hidden_size))
        self.variance_epsilon = eps

    def forward(self, hidden_states: Tensor) -> Tensor:
        input_dtype = hidden_states.dtype
        # Normalise in float32 regardless of the training dtype: the variance of
        # a bf16 tensor is where small models quietly go unstable.
        hidden_states = hidden_states.to(torch.float32)
        variance = hidden_states.pow(2).mean(-1, keepdim=True)
        hidden_states = hidden_states * torch.rsqrt(variance + self.variance_epsilon)
        return (self.weight * hidden_states).to(input_dtype)


class RotaryEmbedding(nn.Module):
    """Rotary position embeddings, in the layout ``transformers`` expects.

    The half-split convention below is what makes exported weights load into
    LlamaForCausalLM without the permutation dance that other RoPE layouts need.
    """

    # Declared so type checkers know register_buffer produced a Tensor.
    inv_freq: Tensor

    def __init__(self, head_dim: int, max_positions: int, theta: float) -> None:
        super().__init__()
        inverse_frequency = 1.0 / (
            theta ** (torch.arange(0, head_dim, 2, dtype=torch.float32) / head_dim)
        )
        self.register_buffer("inv_freq", inverse_frequency, persistent=False)
        self.max_positions = max_positions

    def forward(self, positions: Tensor) -> tuple[Tensor, Tensor]:
        frequencies = positions.float().unsqueeze(-1) * self.inv_freq
        embedding = torch.cat((frequencies, frequencies), dim=-1)
        return embedding.cos(), embedding.sin()


def rotate_half(x: Tensor) -> Tensor:
    first_half = x[..., : x.shape[-1] // 2]
    second_half = x[..., x.shape[-1] // 2 :]
    return torch.cat((-second_half, first_half), dim=-1)


def apply_rotary(query: Tensor, key: Tensor, cos: Tensor, sin: Tensor) -> tuple[Tensor, Tensor]:
    cos = cos.unsqueeze(1)  # broadcast over heads
    sin = sin.unsqueeze(1)
    return (
        query * cos + rotate_half(query) * sin,
        key * cos + rotate_half(key) * sin,
    )


def repeat_kv(hidden_states: Tensor, repeats: int) -> Tensor:
    """Expand grouped key/value heads to match the number of query heads."""

    if repeats == 1:
        return hidden_states
    batch, kv_heads, sequence, head_dim = hidden_states.shape
    expanded = hidden_states[:, :, None, :, :].expand(batch, kv_heads, repeats, sequence, head_dim)
    return expanded.reshape(batch, kv_heads * repeats, sequence, head_dim)


class Attention(nn.Module):
    def __init__(self, config: BreadLMConfig) -> None:
        super().__init__()
        self.config = config
        self.num_heads = config.num_attention_heads
        self.num_kv_heads = config.num_key_value_heads
        self.head_dim = config.head_dim
        self.repeats = self.num_heads // self.num_kv_heads

        self.q_proj = nn.Linear(config.hidden_size, self.num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(self.num_heads * self.head_dim, config.hidden_size, bias=False)

    def forward(self, hidden_states: Tensor, cos: Tensor, sin: Tensor) -> Tensor:
        batch, sequence, _ = hidden_states.shape

        query = self.q_proj(hidden_states).view(batch, sequence, self.num_heads, self.head_dim)
        key = self.k_proj(hidden_states).view(batch, sequence, self.num_kv_heads, self.head_dim)
        value = self.v_proj(hidden_states).view(batch, sequence, self.num_kv_heads, self.head_dim)

        query = query.transpose(1, 2)
        key = key.transpose(1, 2)
        value = value.transpose(1, 2)

        query, key = apply_rotary(query, key, cos, sin)
        key = repeat_kv(key, self.repeats)
        value = repeat_kv(value, self.repeats)

        attended = F.scaled_dot_product_attention(
            query,
            key,
            value,
            dropout_p=self.config.attention_dropout if self.training else 0.0,
            is_causal=True,
        )
        attended = attended.transpose(1, 2).reshape(batch, sequence, -1)
        return self.o_proj(attended)


class FeedForward(nn.Module):
    """SwiGLU: a gated feed-forward block."""

    def __init__(self, config: BreadLMConfig) -> None:
        super().__init__()
        self.gate_proj = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.up_proj = nn.Linear(config.hidden_size, config.intermediate_size, bias=False)
        self.down_proj = nn.Linear(config.intermediate_size, config.hidden_size, bias=False)

    def forward(self, hidden_states: Tensor) -> Tensor:
        return self.down_proj(F.silu(self.gate_proj(hidden_states)) * self.up_proj(hidden_states))


class DecoderLayer(nn.Module):
    def __init__(self, config: BreadLMConfig) -> None:
        super().__init__()
        self.self_attn = Attention(config)
        self.mlp = FeedForward(config)
        self.input_layernorm = RMSNorm(config.hidden_size, config.rms_norm_eps)
        self.post_attention_layernorm = RMSNorm(config.hidden_size, config.rms_norm_eps)

    def forward(self, hidden_states: Tensor, cos: Tensor, sin: Tensor) -> Tensor:
        hidden_states = hidden_states + self.self_attn(
            self.input_layernorm(hidden_states), cos, sin
        )
        return hidden_states + self.mlp(self.post_attention_layernorm(hidden_states))


class BreadLMBody(nn.Module):
    """Named ``model`` so the state dict matches LlamaForCausalLM."""

    def __init__(self, config: BreadLMConfig) -> None:
        super().__init__()
        self.embed_tokens = nn.Embedding(config.vocab_size, config.hidden_size)
        self.layers = nn.ModuleList(DecoderLayer(config) for _ in range(config.num_hidden_layers))
        self.norm = RMSNorm(config.hidden_size, config.rms_norm_eps)


class BreadLM(nn.Module):
    """A decoder-only language model with no inherited weights."""

    def __init__(self, config: BreadLMConfig) -> None:
        super().__init__()
        self.config = config
        self.model = BreadLMBody(config)
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)
        self.rotary = RotaryEmbedding(
            config.head_dim, config.max_position_embeddings, config.rope_theta
        )

        if config.tie_word_embeddings:
            self.lm_head.weight = self.model.embed_tokens.weight

        self.apply(self._init_weights)
        # Scale the residual projections down by depth, so the signal entering
        # the residual stream does not grow with layer count. Without this,
        # deeper models diverge in the first few hundred steps.
        scale = math.sqrt(2 * config.num_hidden_layers)
        for name, parameter in self.named_parameters():
            if name.endswith("o_proj.weight") or name.endswith("down_proj.weight"):
                with torch.no_grad():
                    parameter.div_(scale)

    def _init_weights(self, module: nn.Module) -> None:
        std = self.config.initializer_range
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=std)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=std)

    def forward(self, input_ids: Tensor, labels: Tensor | None = None) -> dict[str, Tensor]:
        _batch, sequence = input_ids.shape
        positions = torch.arange(sequence, device=input_ids.device)
        cos, sin = self.rotary(positions)
        cos = cos.unsqueeze(0)
        sin = sin.unsqueeze(0)

        hidden_states = self.model.embed_tokens(input_ids)
        for layer in self.model.layers:
            hidden_states = layer(hidden_states, cos, sin)
        hidden_states = self.model.norm(hidden_states)
        logits = self.lm_head(hidden_states)

        output: dict[str, Tensor] = {"logits": logits}
        if labels is not None:
            # Standard next-token objective: predict position i+1 from position i.
            shifted_logits = logits[:, :-1, :].contiguous()
            shifted_labels = labels[:, 1:].contiguous()
            output["loss"] = F.cross_entropy(
                shifted_logits.view(-1, shifted_logits.size(-1)),
                shifted_labels.view(-1),
                ignore_index=-100,
            )
        return output

    # ------------------------------------------------------------------ utility
    def parameter_counts(self) -> dict[str, int]:
        total = sum(p.numel() for p in self.parameters())
        embedding = self.model.embed_tokens.weight.numel()
        if not self.config.tie_word_embeddings:
            embedding += self.lm_head.weight.numel()
        return {
            "total": total,
            "embedding": embedding,
            "non_embedding": total - embedding,
        }

    def configure_optimizer(
        self, learning_rate: float, weight_decay: float, betas: tuple[float, float]
    ) -> torch.optim.Optimizer:
        """AdamW with decay on matrices only, not on norms and embeddings."""

        decay, no_decay = [], []
        for name, parameter in self.named_parameters():
            if not parameter.requires_grad:
                continue
            if parameter.dim() >= 2 and "embed_tokens" not in name:
                decay.append(parameter)
            else:
                no_decay.append(parameter)
        return torch.optim.AdamW(
            [
                {"params": decay, "weight_decay": weight_decay},
                {"params": no_decay, "weight_decay": 0.0},
            ],
            lr=learning_rate,
            betas=betas,
            eps=1e-8,
        )

    @torch.no_grad()
    def generate(
        self,
        input_ids: Tensor,
        max_new_tokens: int = 64,
        temperature: float = 0.8,
        top_k: int | None = 50,
        eos_token_id: int | None = None,
    ) -> Tensor:
        """Sample continuations. Deliberately simple: no KV cache.

        Training is what this file is for. For fast inference, export to
        Transformers and use the cached implementation there.
        """

        self.eval()
        window = self.config.max_position_embeddings

        for _ in range(max_new_tokens):
            cropped = input_ids[:, -window:]
            logits = self.forward(cropped)["logits"][:, -1, :]

            if temperature <= 0:
                next_token = logits.argmax(dim=-1, keepdim=True)
            else:
                logits = logits / temperature
                if top_k is not None:
                    top_values, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                    logits = logits.masked_fill(logits < top_values[:, [-1]], float("-inf"))
                probabilities = F.softmax(logits, dim=-1)
                next_token = torch.multinomial(probabilities, num_samples=1)

            input_ids = torch.cat((input_ids, next_token), dim=1)
            if eos_token_id is not None and bool((next_token == eos_token_id).all()):
                break

        return input_ids


@dataclass
class ComputeBudget:
    """Estimates for what a given model and token budget will cost.

    The FLOP figure uses the standard 6ND approximation for a forward and
    backward pass. It is an estimate, not a measurement: the trainer reports the
    throughput it actually achieves and projects from that instead.
    """

    parameters: int
    tokens: int
    achieved_tokens_per_second: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def training_flops(self) -> float:
        return 6.0 * self.parameters * self.tokens

    @property
    def chinchilla_tokens(self) -> int:
        """Roughly compute-optimal token count: about 20 per parameter."""

        return 20 * self.parameters

    @property
    def estimated_seconds(self) -> float | None:
        if not self.achieved_tokens_per_second:
            return None
        return self.tokens / self.achieved_tokens_per_second

    def summary(self) -> dict[str, Any]:
        seconds = self.estimated_seconds
        return {
            "parameters": self.parameters,
            "tokens": self.tokens,
            "tokens_per_parameter": round(self.tokens / max(self.parameters, 1), 1),
            "chinchilla_tokens": self.chinchilla_tokens,
            "training_flops": self.training_flops,
            "estimated_hours": round(seconds / 3600, 2) if seconds else None,
        }
