"""Document upload, indexing and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlmodel import Session, col, select

from ..audit import record_action
from ..config import Settings, get_settings
from ..db import get_session
from ..errors import NotFoundError, ValidationFailedError
from ..models import Document, KnowledgeSpace
from ..schemas import (
    Citation,
    DeleteResponse,
    DocumentIndexRequest,
    DocumentIndexResponse,
    DocumentOut,
    DocumentUploadResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from ..services.rag import ingest
from ..services.rag.loaders import (
    LANGUAGE_BY_EXTENSION,
    check_extension,
    hash_bytes,
    resolve_upload_path,
)

router = APIRouter(tags=["documents"])


def _default_space(session: Session, space_id: str | None) -> KnowledgeSpace:
    if space_id:
        space = session.get(KnowledgeSpace, space_id)
        if space is None:
            raise NotFoundError(f"Knowledge space {space_id} does not exist.")
        return space
    space = session.exec(select(KnowledgeSpace).order_by(col(KnowledgeSpace.created_at))).first()
    if space is None:
        raise NotFoundError(
            "No knowledge space exists yet.",
            hint="Create one with POST /api/knowledge-spaces.",
        )
    return space


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    summary="Upload files into a knowledge space",
)
async def upload_documents(
    files: list[UploadFile] = File(..., description="One or more supported text/code/PDF files"),
    knowledge_space_id: str | None = Form(default=None),
    index_now: bool = Form(default=True),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    """Store uploads on disk and optionally index them straight away.

    Uploaded code is treated as data: it is read, hashed and embedded, never
    imported or executed. Filenames are rebuilt from a sanitised basename, so a
    name like ``../../.ssh/authorized_keys`` cannot escape the uploads folder.
    """

    space = _default_space(session, knowledge_space_id)
    stored: list[Document] = []
    skipped: list[dict[str, str]] = []

    for upload in files:
        original_name = upload.filename or "upload.txt"
        try:
            extension = check_extension(original_name)
        except ValidationFailedError as exc:
            skipped.append({"filename": original_name, "reason": exc.message})
            continue

        payload = await upload.read()
        if len(payload) > settings.max_upload_bytes:
            skipped.append(
                {
                    "filename": original_name,
                    "reason": f"File is {len(payload) // 1024} KB; the limit is "
                    f"{settings.max_upload_bytes // 1024} KB "
                    "(raise BREAD_MAX_UPLOAD_BYTES to change it).",
                }
            )
            continue
        if not payload:
            skipped.append({"filename": original_name, "reason": "The file is empty."})
            continue

        digest = hash_bytes(payload)
        duplicate = session.exec(
            select(Document)
            .where(Document.knowledge_space_id == space.id)
            .where(Document.content_hash == digest)
        ).first()
        if duplicate is not None:
            skipped.append(
                {
                    "filename": original_name,
                    "reason": f"Identical content is already indexed as '{duplicate.filename}'.",
                }
            )
            continue

        target = resolve_upload_path(settings.uploads_dir, original_name)
        target.write_bytes(payload)

        document = Document(
            knowledge_space_id=space.id,
            filename=target.name,
            stored_path=str(target),
            extension=extension,
            media_type=upload.content_type,
            size_bytes=len(payload),
            content_hash=digest,
            language=LANGUAGE_BY_EXTENSION.get(extension, "text"),
            status="uploaded",
        )
        session.add(document)
        stored.append(document)

    session.commit()
    for document in stored:
        session.refresh(document)

    if index_now and stored:
        ingest.index_documents(session, settings, stored)
        for document in stored:
            session.refresh(document)

    if stored:
        record_action(
            session,
            "document.upload",
            target_type="knowledge_space",
            target_id=space.id,
            detail={"count": len(stored), "skipped": len(skipped)},
        )

    return DocumentUploadResponse(
        documents=[DocumentOut(**document.model_dump()) for document in stored],
        skipped=skipped,
    )


@router.post(
    "/documents/index",
    response_model=DocumentIndexResponse,
    summary="(Re)build the vector index for documents",
)
def index_documents(
    payload: DocumentIndexRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DocumentIndexResponse:
    if payload.document_ids:
        documents = [
            document
            for document in (
                session.get(Document, document_id) for document_id in payload.document_ids
            )
            if document is not None
        ]
    else:
        space = _default_space(session, payload.knowledge_space_id)
        documents = list(
            session.exec(select(Document).where(Document.knowledge_space_id == space.id)).all()
        )

    if not documents:
        raise NotFoundError("There are no documents to index.")

    result = ingest.index_documents(session, settings, documents, force=payload.force)
    record_action(
        session,
        "document.index",
        target_type="knowledge_space",
        target_id=documents[0].knowledge_space_id,
        detail=result,
    )
    return DocumentIndexResponse(**result)


@router.get("/documents", response_model=list[DocumentOut], summary="List documents")
def list_documents(
    knowledge_space_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[DocumentOut]:
    statement = select(Document)
    if knowledge_space_id:
        statement = statement.where(Document.knowledge_space_id == knowledge_space_id)
    statement = statement.order_by(col(Document.created_at).desc())
    return [DocumentOut(**document.model_dump()) for document in session.exec(statement).all()]


@router.delete(
    "/documents/{document_id}",
    response_model=DeleteResponse,
    summary="Delete a document",
)
def delete_document(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} does not exist.")
    ingest.remove_document(session, settings, document)
    record_action(session, "document.delete", target_type="document", target_id=document_id)
    return DeleteResponse(deleted=True, id=document_id)


@router.post("/rag/search", response_model=RagSearchResponse, summary="Search a knowledge space")
def rag_search(
    payload: RagSearchRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RagSearchResponse:
    citations, embedding_model_id, reranked = ingest.search(
        session,
        settings,
        query=payload.query,
        space_id=payload.knowledge_space_id,
        top_k=payload.top_k,
        rerank=payload.rerank,
    )
    return RagSearchResponse(
        query=payload.query,
        knowledge_space_id=payload.knowledge_space_id,
        results=[Citation(**citation) for citation in citations],
        embedding_model_id=embedding_model_id,
        reranked=reranked,
    )
