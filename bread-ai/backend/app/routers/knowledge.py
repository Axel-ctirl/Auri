"""Knowledge space management."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..audit import record_action
from ..config import Settings, get_settings
from ..db import get_session
from ..errors import NotFoundError
from ..models import KnowledgeSpace, utcnow
from ..schemas import (
    DeleteResponse,
    KnowledgeSpaceCreate,
    KnowledgeSpaceOut,
    KnowledgeSpaceUpdate,
)
from ..services.rag import ingest

router = APIRouter(prefix="/knowledge-spaces", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeSpaceOut], summary="List knowledge spaces")
def list_spaces(session: Session = Depends(get_session)) -> list[KnowledgeSpaceOut]:
    spaces = session.exec(select(KnowledgeSpace).order_by(col(KnowledgeSpace.created_at))).all()
    return [KnowledgeSpaceOut(**space.model_dump()) for space in spaces]


@router.post("", response_model=KnowledgeSpaceOut, summary="Create a knowledge space")
def create_space(
    payload: KnowledgeSpaceCreate,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeSpaceOut:
    space = KnowledgeSpace(
        name=payload.name,
        description=payload.description,
        embedding_model_id=settings.embedding_model_id,
        chunk_size=payload.chunk_size or settings.chunk_size,
        chunk_overlap=payload.chunk_overlap or settings.chunk_overlap,
    )
    session.add(space)
    session.commit()
    session.refresh(space)
    record_action(
        session,
        "knowledge_space.create",
        target_type="knowledge_space",
        target_id=space.id,
        detail={"name": space.name},
    )
    return KnowledgeSpaceOut(**space.model_dump())


@router.patch("/{space_id}", response_model=KnowledgeSpaceOut, summary="Update a space")
def update_space(
    space_id: str,
    payload: KnowledgeSpaceUpdate,
    session: Session = Depends(get_session),
) -> KnowledgeSpaceOut:
    space = session.get(KnowledgeSpace, space_id)
    if space is None:
        raise NotFoundError(f"Knowledge space {space_id} does not exist.")
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(space, field, value)
    space.updated_at = utcnow()
    session.add(space)
    session.commit()
    session.refresh(space)
    return KnowledgeSpaceOut(**space.model_dump())


@router.delete("/{space_id}", response_model=DeleteResponse, summary="Delete a space")
def delete_space(
    space_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    """Removes the space, its documents, their chunks, their vectors and their files."""

    space = session.get(KnowledgeSpace, space_id)
    if space is None:
        raise NotFoundError(f"Knowledge space {space_id} does not exist.")
    ingest.remove_space(session, settings, space)
    record_action(
        session,
        "knowledge_space.delete",
        target_type="knowledge_space",
        target_id=space_id,
    )
    return DeleteResponse(deleted=True, id=space_id)
