"""Pretraining Bread's own language models from random initialisation.

Nothing in this package starts from someone else's weights. It contains the
model, the tokenizer and data pipeline, and the training loop needed to produce
a model whose every parameter was learned from data you chose.

See docs/PRETRAINING.md for what is achievable on one GPU, stated honestly.
"""

from .data import (
    BOS_ID,
    EOS_ID,
    PAD_ID,
    UNK_ID,
    PackResult,
    decode,
    encode,
    held_out_split,
    iter_batches,
    load_tokenizer,
    open_shard,
    pack_documents,
    shard_token_count,
    train_tokenizer,
)
from .model import BreadLM, BreadLMConfig, ComputeBudget
from .train import PretrainConfig, evaluate, learning_rate_at, pretrain

__all__ = [
    "BOS_ID",
    "EOS_ID",
    "PAD_ID",
    "UNK_ID",
    "BreadLM",
    "BreadLMConfig",
    "ComputeBudget",
    "PackResult",
    "PretrainConfig",
    "decode",
    "encode",
    "evaluate",
    "held_out_split",
    "iter_batches",
    "learning_rate_at",
    "load_tokenizer",
    "open_shard",
    "pack_documents",
    "pretrain",
    "shard_token_count",
    "train_tokenizer",
]
