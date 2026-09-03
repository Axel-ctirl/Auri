"""Indexing and retrieval pipeline for knowledge spaces."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from sqlmodel import Session, delete, select

from ...config import Settings
from ...errors import NotFoundError
from ...models import Document, DocumentChunk, KnowledgeSpace, utcnow
from .chunking import chunk_text
from .embeddings import HASHING_MODEL_ID, get_embedder
from .loaders import load_document
from .store import SearchHit, VectorRecord, get_vector_store

EXCERPT_CHARS = 600


def _store(settings: Settings):
    return get_vector_store(settings.vector_backend, settings.vector_dir)


def _embedder(settings: Settings):
    return get_embedder(
        settings.embedding_model_id,
        settings.embedding_backend,
        allow_download=settings.allow_model_download,
    )


def embedding_notice(settings: Settings) -> str | None:
    """Warn when search is running on the low-quality fallback encoder."""

    if _embedder(settings).model_id == HASHING_MODEL_ID:
        return (
            "Retrieval is using Bread's hashing fallback because "
            f"'{settings.embedding_model_id}' is not in the local cache. Results are "
            "keyword-ish rather than semantic. Install sentence-transformers and "
            "download the model, then re-index."
        )
    return None


def index_documents(
    session: Session,
    settings: Settings,
    documents: list[Document],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Chunk, embed and store the given documents. Skips unchanged files."""

    started = time.perf_counter()
    embedder = _embedder(settings)
    store = _store(settings)

    indexed = 0
    skipped = 0
    created_chunks = 0
    failures: list[dict[str, str]] = []

    for document in documents:
        space = session.get(KnowledgeSpace, document.knowledge_space_id)
        if space is None:
            failures.append({"document_id": document.id, "error": "knowledge space missing"})
            continue

        path = Path(document.stored_path)
        if not path.exists():
            document.status = "failed"
            document.error = "The stored file is gone from disk."
            session.add(document)
            failures.append({"document_id": document.id, "error": document.error})
            continue

        try:
            loaded = load_document(path)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            document.status = "failed"
            document.error = str(exc)
            session.add(document)
            failures.append({"document_id": document.id, "error": str(exc)})
            continue

        already_indexed = document.status == "indexed" and document.content_hash == loaded.content_hash
        if already_indexed and not force:
            skipped += 1
            continue

        # Replace any previous vectors for this document so re-indexing is not additive.
        store.delete_document(space.id, document.id)
        session.exec(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))

        chunks = chunk_text(
            loaded.text,
            chunk_size=space.chunk_size or settings.chunk_size,
            chunk_overlap=space.chunk_overlap or settings.chunk_overlap,
            extension=loaded.extension,
        )

        if not chunks:
            document.status = "skipped"
            document.error = "No indexable text was found in this file."
            document.chunk_count = 0
            document.content_hash = loaded.content_hash
            session.add(document)
            skipped += 1
            continue

        rows: list[DocumentChunk] = []
        for chunk in chunks:
            rows.append(
                DocumentChunk(
                    document_id=document.id,
                    knowledge_space_id=space.id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    token_estimate=chunk.token_estimate,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                )
            )
        session.add_all(rows)
        session.flush()

        vectors = embedder.embed([row.content for row in rows])
        store.add(
            space.id,
            [
                VectorRecord(
                    chunk_id=row.id,
                    document_id=document.id,
                    chunk_index=row.chunk_index,
                    text=row.content,
                )
                for row in rows
            ],
            np.asarray(vectors, dtype=np.float32),
        )

        document.status = "indexed"
        document.error = None
        document.chunk_count = len(rows)
        document.content_hash = loaded.content_hash
        document.language = loaded.language
        document.indexed_at = utcnow()
        session.add(document)

        indexed += 1
        created_chunks += len(rows)

    session.commit()
    _refresh_space_counters(session, {document.knowledge_space_id for document in documents})

    return {
        "indexed_documents": indexed,
        "created_chunks": created_chunks,
        "skipped_documents": skipped,
        "failed": failures,
        "embedding_model_id": embedder.model_id,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _refresh_space_counters(session: Session, space_ids: set[str]) -> None:
    for space_id in space_ids:
        space = session.get(KnowledgeSpace, space_id)
        if space is None:
            continue
        documents = session.exec(
            select(Document).where(Document.knowledge_space_id == space_id)
        ).all()
        space.document_count = len(documents)
        space.chunk_count = sum(document.chunk_count for document in documents)
        space.updated_at = utcnow()
        session.add(space)
    session.commit()


def search(
    session: Session,
    settings: Settings,
    *,
    query: str,
    space_id: str | None,
    top_k: int,
    rerank: bool | None = None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Return citation dicts, the embedding model used, and whether reranking ran."""

    if not space_id:
        space = session.exec(select(KnowledgeSpace).order_by(KnowledgeSpace.created_at)).first()
        if space is None:
            return [], "", False
        space_id = space.id
    elif session.get(KnowledgeSpace, space_id) is None:
        raise NotFoundError(f"Knowledge space {space_id} does not exist.")

    embedder = _embedder(settings)
    store = _store(settings)
    query_vector = embedder.embed([query])[0]

    should_rerank = settings.rag_rerank_enabled if rerank is None else rerank
    fetch_k = top_k * 4 if should_rerank else top_k
    hits = store.search(space_id, query_vector, max(fetch_k, top_k))

    reranked = False
    if should_rerank and hits:
        hits, reranked = _rerank(query, hits, settings)
    hits = hits[:top_k]

    citations: list[dict[str, Any]] = []
    for hit in hits:
        chunk = session.get(DocumentChunk, hit.chunk_id)
        document = session.get(Document, hit.document_id)
        if chunk is None or document is None:
            continue
        citations.append(
            {
                "document_id": document.id,
                "document_name": document.filename,
                "chunk_id": chunk.id,
                "chunk_index": chunk.chunk_index,
                "score": round(hit.score, 4),
                "excerpt": chunk.content[:EXCERPT_CHARS],
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            }
        )
    return citations, embedder.model_id, reranked


def _rerank(query: str, hits: list[SearchHit], settings: Settings) -> tuple[list[SearchHit], bool]:
    """Cross-encoder reranking when the model is available; otherwise a no-op."""

    try:
        from sentence_transformers import CrossEncoder

        encoder = CrossEncoder(settings.rag_rerank_model_id, local_files_only=True)
    except Exception:
        return hits, False

    scores = encoder.predict([(query, hit.text) for hit in hits])
    ordered = sorted(zip(hits, scores), key=lambda pair: float(pair[1]), reverse=True)
    rescored = []
    for hit, score in ordered:
        hit.score = float(score)
        rescored.append(hit)
    return rescored, True


def remove_document(session: Session, settings: Settings, document: Document) -> None:
    """Delete a document, its chunks, its vectors and its file on disk."""

    _store(settings).delete_document(document.knowledge_space_id, document.id)
    session.exec(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))

    stored = Path(document.stored_path)
    uploads_root = settings.uploads_dir.resolve()
    try:
        resolved = stored.resolve()
        if stored.exists() and uploads_root in resolved.parents:
            resolved.unlink()
    except OSError:
        # A locked or already-removed file must not block the database delete.
        pass

    space_id = document.knowledge_space_id
    session.delete(document)
    session.commit()
    _refresh_space_counters(session, {space_id})


def remove_space(session: Session, settings: Settings, space: KnowledgeSpace) -> None:
    documents = session.exec(
        select(Document).where(Document.knowledge_space_id == space.id)
    ).all()
    for document in documents:
        remove_document(session, settings, document)
    _store(settings).delete_space(space.id)
    session.delete(space)
    session.commit()


def build_context_block(citations: list[dict[str, Any]]) -> str:
    """Render retrieved chunks as a labelled block the model can cite back."""

    if not citations:
        return ""
    parts = ["Retrieved context from the selected knowledge space:"]
    for position, citation in enumerate(citations, start=1):
        location = ""
        if citation.get("start_line"):
            location = f" lines {citation['start_line']}-{citation['end_line']}"
        parts.append(
            f"\n[{position}] {citation['document_name']} "
            f"(chunk {citation['chunk_index']}{location})\n"
            f"{citation['excerpt']}"
        )
    parts.append(
        "\nUse this context when it is relevant and cite it as [1], [2] and so on. "
        "If it does not answer the question, say so instead of guessing."
    )
    return "\n".join(parts)
