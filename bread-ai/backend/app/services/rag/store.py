"""Vector storage for knowledge spaces.

The default store is a plain NumPy matrix per knowledge space, persisted to
``data/vectors/<space_id>/``. It has no server, no daemon and no network
listener, which suits a personal index of a few hundred thousand chunks. Set
``VECTOR_BACKEND=chroma`` to use ChromaDB's persistent client instead.
"""

from __future__ import annotations

import contextlib
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ...errors import BackendUnavailableError


@dataclass
class VectorRecord:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    chunk_index: int
    score: float
    text: str


class VectorStore(ABC):
    @abstractmethod
    def add(self, space_id: str, records: list[VectorRecord], vectors: np.ndarray) -> None: ...

    @abstractmethod
    def search(self, space_id: str, query_vector: np.ndarray, top_k: int) -> list[SearchHit]: ...

    @abstractmethod
    def delete_document(self, space_id: str, document_id: str) -> int: ...

    @abstractmethod
    def delete_space(self, space_id: str) -> None: ...

    @abstractmethod
    def count(self, space_id: str) -> int: ...


class NumpyVectorStore(VectorStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _space_dir(self, space_id: str) -> Path:
        # space_id is a server-generated uuid hex, never user text.
        path = self.root / space_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self, space_id: str) -> tuple[np.ndarray, list[dict]]:
        space_dir = self._space_dir(space_id)
        vectors_path = space_dir / "vectors.npy"
        meta_path = space_dir / "meta.json"
        if not vectors_path.exists() or not meta_path.exists():
            return np.zeros((0, 0), dtype=np.float32), []
        vectors = np.load(vectors_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if len(meta) != vectors.shape[0]:
            # A crash between the two writes would desync them; the index is
            # rebuildable, so drop it rather than serve wrong citations.
            return np.zeros((0, 0), dtype=np.float32), []
        return vectors.astype(np.float32), meta

    def _save(self, space_id: str, vectors: np.ndarray, meta: list[dict]) -> None:
        space_dir = self._space_dir(space_id)
        np.save(space_dir / "vectors.npy", vectors.astype(np.float32))
        (space_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def add(self, space_id: str, records: list[VectorRecord], vectors: np.ndarray) -> None:
        if not records:
            return
        with self._lock:
            existing_vectors, existing_meta = self._load(space_id)
            new_meta = [
                {
                    "chunk_id": record.chunk_id,
                    "document_id": record.document_id,
                    "chunk_index": record.chunk_index,
                    "text": record.text,
                }
                for record in records
            ]
            if existing_vectors.size == 0:
                merged_vectors = vectors.astype(np.float32)
                merged_meta = new_meta
            else:
                if existing_vectors.shape[1] != vectors.shape[1]:
                    raise ValueError(
                        "Embedding dimension changed for this knowledge space. "
                        "Re-index it after switching embedding models."
                    )
                merged_vectors = np.vstack([existing_vectors, vectors.astype(np.float32)])
                merged_meta = existing_meta + new_meta
            self._save(space_id, merged_vectors, merged_meta)

    def search(self, space_id: str, query_vector: np.ndarray, top_k: int) -> list[SearchHit]:
        with self._lock:
            vectors, meta = self._load(space_id)
        if vectors.size == 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.shape[0] != vectors.shape[1]:
            return []
        scores = vectors @ query
        top_k = min(top_k, scores.shape[0])
        best = np.argpartition(-scores, top_k - 1)[:top_k]
        best = best[np.argsort(-scores[best])]
        return [
            SearchHit(
                chunk_id=meta[i]["chunk_id"],
                document_id=meta[i]["document_id"],
                chunk_index=meta[i]["chunk_index"],
                score=float(scores[i]),
                text=meta[i]["text"],
            )
            for i in best
        ]

    def delete_document(self, space_id: str, document_id: str) -> int:
        with self._lock:
            vectors, meta = self._load(space_id)
            if not meta:
                return 0
            keep = [i for i, entry in enumerate(meta) if entry["document_id"] != document_id]
            removed = len(meta) - len(keep)
            if removed == 0:
                return 0
            self._save(
                space_id,
                (vectors[keep] if keep else np.zeros((0, vectors.shape[1]), dtype=np.float32)),
                [meta[i] for i in keep],
            )
            return removed

    def delete_space(self, space_id: str) -> None:
        with self._lock:
            space_dir = self.root / space_id
            for name in ("vectors.npy", "meta.json"):
                target = space_dir / name
                if target.exists():
                    target.unlink()
            if space_dir.exists() and not any(space_dir.iterdir()):
                space_dir.rmdir()

    def count(self, space_id: str) -> int:
        with self._lock:
            _, meta = self._load(space_id)
            return len(meta)


class ChromaVectorStore(VectorStore):
    """ChromaDB persistent client. Enabled with ``VECTOR_BACKEND=chroma``."""

    def __init__(self, root: Path) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise BackendUnavailableError(
                "VECTOR_BACKEND=chroma but chromadb is not installed.",
                hint="pip install chromadb, or set VECTOR_BACKEND=numpy.",
            ) from exc
        self._client = chromadb.PersistentClient(path=str(root))

    def _collection(self, space_id: str):
        return self._client.get_or_create_collection(
            name=f"space_{space_id}", metadata={"hnsw:space": "cosine"}
        )

    def add(self, space_id: str, records: list[VectorRecord], vectors: np.ndarray) -> None:
        if not records:
            return
        self._collection(space_id).upsert(
            ids=[record.chunk_id for record in records],
            embeddings=[vector.tolist() for vector in np.asarray(vectors, dtype=np.float32)],
            documents=[record.text for record in records],
            metadatas=[
                {"document_id": record.document_id, "chunk_index": record.chunk_index}
                for record in records
            ],
        )

    def search(self, space_id: str, query_vector: np.ndarray, top_k: int) -> list[SearchHit]:
        result = self._collection(space_id).query(
            query_embeddings=[np.asarray(query_vector, dtype=np.float32).reshape(-1).tolist()],
            n_results=top_k,
        )
        hits: list[SearchHit] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    document_id=str(metadata.get("document_id", "")),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    score=1.0 - float(distances[index]),
                    text=documents[index],
                )
            )
        return hits

    def delete_document(self, space_id: str, document_id: str) -> int:
        collection = self._collection(space_id)
        matching = collection.get(where={"document_id": document_id})
        ids = matching.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def delete_space(self, space_id: str) -> None:
        # Deleting a collection that was never created is not an error here.
        with contextlib.suppress(Exception):  # pragma: no cover
            self._client.delete_collection(name=f"space_{space_id}")

    def count(self, space_id: str) -> int:
        return int(self._collection(space_id).count())


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_vector_store(backend: str, root: Path) -> VectorStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ChromaVectorStore(root) if backend == "chroma" else NumpyVectorStore(root)
        return _store


def reset_vector_store() -> None:
    global _store
    with _store_lock:
        _store = None
