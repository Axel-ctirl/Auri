"""Tokenizer training and data packing for Bread's from-scratch models.

Two jobs live here.

**Training a tokenizer.** A model trained from nothing needs its own vocabulary,
learned from the same text it will be trained on. A tokenizer built on your code
and your prose spends its vocabulary on the identifiers and words you actually
use, which is worth several percent of effective context.

**Packing.** Pretraining reads a flat stream of token ids, not a list of
documents. Text is tokenized once, concatenated with an end-of-document token
between records, and written to a memory-mapped binary file. Training then draws
random windows from it. The point is that a 20-billion-token corpus never has to
fit in RAM: the operating system pages in the few megabytes each batch touches.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PAD_TOKEN = "<|pad|>"
BOS_TOKEN = "<|bos|>"
EOS_TOKEN = "<|eos|>"
UNK_TOKEN = "<|unk|>"
SPECIAL_TOKENS = [PAD_TOKEN, BOS_TOKEN, EOS_TOKEN, UNK_TOKEN]

PAD_ID, BOS_ID, EOS_ID, UNK_ID = 0, 1, 2, 3


def token_dtype(vocab_size: int) -> np.dtype:
    """uint16 up to 65,535 tokens, which halves the size of a packed corpus."""

    return np.dtype(np.uint16) if vocab_size < 2**16 else np.dtype(np.uint32)


# --------------------------------------------------------------------- tokenizer
def train_tokenizer(
    texts: Iterable[str],
    output_dir: Path,
    vocab_size: int = 32000,
    min_frequency: int = 2,
) -> Path:
    """Train a byte-level BPE tokenizer and save it in Transformers' format."""

    try:
        from tokenizers import Tokenizer, decoders, models, pre_tokenizers, processors, trainers
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Training a tokenizer needs the 'tokenizers' package. pip install tokenizers"
        ) from exc

    tokenizer = Tokenizer(models.BPE(unk_token=None))
    # Byte level means every possible byte is representable, so no input is ever
    # out-of-vocabulary. That matters for source code, which is full of symbols a
    # word-level vocabulary would drop.
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    tokenizer.post_processor = processors.ByteLevel(trim_offsets=False)

    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=min_frequency,
        special_tokens=SPECIAL_TOKENS,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
    )
    tokenizer.train_from_iterator(texts, trainer=trainer)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer_path = output_dir / "tokenizer.json"
    tokenizer.save(str(tokenizer_path))

    # The sidecar files Transformers looks for when loading a fast tokenizer.
    (output_dir / "special_tokens_map.json").write_text(
        json.dumps(
            {
                "pad_token": PAD_TOKEN,
                "bos_token": BOS_TOKEN,
                "eos_token": EOS_TOKEN,
                "unk_token": UNK_TOKEN,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "tokenizer_config.json").write_text(
        json.dumps(
            {
                "tokenizer_class": "PreTrainedTokenizerFast",
                "model_max_length": 1_000_000,
                "pad_token": PAD_TOKEN,
                "bos_token": BOS_TOKEN,
                "eos_token": EOS_TOKEN,
                "unk_token": UNK_TOKEN,
                "clean_up_tokenization_spaces": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return tokenizer_path


def load_tokenizer(tokenizer_dir: Path):
    """Load a trained tokenizer, preferring the Transformers wrapper."""

    tokenizer_dir = Path(tokenizer_dir)
    path = tokenizer_dir if tokenizer_dir.is_dir() else tokenizer_dir.parent

    try:
        from transformers import PreTrainedTokenizerFast

        return PreTrainedTokenizerFast.from_pretrained(str(path))
    except Exception:
        from tokenizers import Tokenizer

        return Tokenizer.from_file(str(path / "tokenizer.json"))


def encode(tokenizer: Any, text: str) -> list[int]:
    """Encode with either wrapper, without adding special tokens."""

    if hasattr(tokenizer, "encode") and hasattr(tokenizer, "convert_ids_to_tokens"):
        return list(tokenizer.encode(text, add_special_tokens=False))
    return list(tokenizer.encode(text).ids)


def decode(tokenizer: Any, ids: list[int]) -> str:
    if hasattr(tokenizer, "convert_ids_to_tokens"):
        return str(tokenizer.decode(ids, skip_special_tokens=True))
    return str(tokenizer.decode(ids))


# ----------------------------------------------------------------------- packing
@dataclass
class PackResult:
    path: Path
    token_count: int
    document_count: int
    dtype: str
    truncated_documents: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "token_count": self.token_count,
            "document_count": self.document_count,
            "dtype": self.dtype,
            "truncated_documents": self.truncated_documents,
        }


def pack_documents(
    documents: Iterable[str],
    tokenizer: Any,
    output_path: Path,
    vocab_size: int,
    *,
    max_document_tokens: int | None = None,
    flush_every: int = 2000,
) -> PackResult:
    """Tokenize documents into one flat binary stream of ids.

    Documents are separated by an end-of-document token so the model learns where
    a document stops rather than running two unrelated files together.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dtype = token_dtype(vocab_size)

    buffer: list[int] = []
    token_count = 0
    document_count = 0
    truncated = 0

    with output_path.open("wb") as handle:
        for document in documents:
            if not document or not document.strip():
                continue
            ids = encode(tokenizer, document)
            if max_document_tokens is not None and len(ids) > max_document_tokens:
                ids = ids[:max_document_tokens]
                truncated += 1

            buffer.extend(ids)
            buffer.append(EOS_ID)
            document_count += 1

            if len(buffer) >= flush_every:
                array = np.asarray(buffer, dtype=dtype)
                array.tofile(handle)
                token_count += array.size
                buffer.clear()

        if buffer:
            array = np.asarray(buffer, dtype=dtype)
            array.tofile(handle)
            token_count += array.size

    return PackResult(
        path=output_path,
        token_count=token_count,
        document_count=document_count,
        dtype=dtype.name,
        truncated_documents=truncated,
    )


def open_shard(path: Path, vocab_size: int) -> np.memmap:
    """Map a packed corpus without reading it into memory."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No packed corpus at {path}")
    return np.memmap(path, dtype=token_dtype(vocab_size), mode="r")


def shard_token_count(path: Path, vocab_size: int) -> int:
    return os.path.getsize(Path(path)) // token_dtype(vocab_size).itemsize


def iter_batches(
    shard: np.ndarray,
    *,
    batch_size: int,
    sequence_length: int,
    seed: int = 0,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield random windows forever, as ``(inputs, targets)``.

    Windows are drawn uniformly rather than swept in order. Over a long run that
    covers the corpus evenly, and it avoids the pathology where the model sees
    the whole first shard before any of the last.
    """

    if shard.size <= sequence_length + 1:
        raise ValueError(
            f"The corpus holds {shard.size} tokens, which is smaller than one "
            f"window of {sequence_length + 1}. Pack more data."
        )

    rng = np.random.default_rng(seed)
    highest_start = shard.size - sequence_length - 1

    while True:
        starts = rng.integers(0, highest_start, size=batch_size)
        inputs = np.stack([shard[start : start + sequence_length] for start in starts])
        targets = np.stack(
            [shard[start + 1 : start + sequence_length + 1] for start in starts]
        )
        yield inputs.astype(np.int64), targets.astype(np.int64)


def held_out_split(
    shard: np.ndarray,
    fraction: float = 0.005,
    minimum_tokens: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Split the tail off for evaluation, so eval text is never trained on.

    On a large corpus the fraction decides the size. On a small one the fraction
    can produce a slice narrower than a single training window, which makes
    evaluation impossible; ``minimum_tokens`` raises the floor. The split never
    takes more than half, because a corpus that small has a different problem.
    """

    if shard.size < 4:
        return shard, shard[:0]

    wanted = max(int(shard.size * fraction), minimum_tokens)
    evaluation_size = min(wanted, shard.size // 2)
    cutoff = max(shard.size - evaluation_size, 1)
    return shard[:cutoff], shard[cutoff:]
