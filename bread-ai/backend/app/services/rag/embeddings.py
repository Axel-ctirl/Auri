"""Local text embeddings.

Two implementations ship with Bread:

``SentenceTransformerEmbedder``
    The real one. Needs ``sentence-transformers`` and a model in the local
    Hugging Face cache.

``HashingEmbedder``
    A dependency-light fallback that hashes character n-grams into a fixed
    vector. It keeps search working offline and on a fresh clone, but its recall
    is clearly worse than a trained encoder. Bread always reports which one
    produced an index so results are never silently mislabelled.
"""

from __future__ import annotations

import hashlib
import itertools
import re
import threading
from typing import Protocol

import numpy as np

_lock = threading.Lock()
_cache: dict[str, Embedder] = {}

HASHING_MODEL_ID = "bread/hashing-fallback"
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class Embedder(Protocol):
    model_id: str
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashingEmbedder:
    """Hashed bag of word and character n-grams, L2 normalised."""

    def __init__(self, dimension: int = 512) -> None:
        self.model_id = HASHING_MODEL_ID
        self.dimension = dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature, weight in _features(text):
                bucket = (
                    int.from_bytes(
                        hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(),
                        "little",
                    )
                    % self.dimension
                )
                matrix[row, bucket] += weight
        return _normalize(matrix)


def _features(text: str) -> list[tuple[str, float]]:
    lowered = text.lower()
    tokens = _TOKEN_RE.findall(lowered)
    features: list[tuple[str, float]] = [(token, 1.0) for token in tokens]
    features.extend((f"{a}_{b}", 0.6) for a, b in itertools.pairwise(tokens))
    # Character 4-grams give the fallback a little robustness to typos and to
    # identifiers that differ only by a suffix.
    compact = re.sub(r"\s+", " ", lowered)
    features.extend((f"#{compact[i:i + 4]}", 0.25) for i in range(0, max(len(compact) - 3, 0), 2))
    return features


class SentenceTransformerEmbedder:
    def __init__(self, model_id: str, allow_download: bool = False) -> None:
        from sentence_transformers import SentenceTransformer

        kwargs = {} if allow_download else {"local_files_only": True}
        self._model = SentenceTransformer(model_id, **kwargs)
        self.model_id = model_id
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


def get_embedder(
    model_id: str,
    backend: str = "auto",
    *,
    allow_download: bool = False,
) -> Embedder:
    """Return a cached embedder, falling back to hashing when needed."""

    cache_key = f"{backend}:{model_id}:{allow_download}"
    with _lock:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        embedder: Embedder
        if backend == "hashing":
            embedder = HashingEmbedder()
        else:
            try:
                embedder = SentenceTransformerEmbedder(model_id, allow_download=allow_download)
            except Exception:
                if backend == "sentence_transformers":
                    raise
                # 'auto' degrades instead of failing: a fresh clone with no model
                # cache still gets working search.
                embedder = HashingEmbedder()

        _cache[cache_key] = embedder
        return embedder


def clear_embedder_cache() -> None:
    with _lock:
        _cache.clear()
