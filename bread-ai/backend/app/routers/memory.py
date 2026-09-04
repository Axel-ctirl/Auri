"""Memory endpoints: what Bread carries between conversations.

The same rows the CLI reads and writes. Nothing here infers a memory on its own:
an entry exists because someone asked for it, and deleting it removes it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..config import Settings, get_settings
from ..db import get_session
from ..errors import NotFoundError, ValidationFailedError
from ..schemas import (
    MemoryCreateRequest,
    MemoryDeleteResponse,
    MemoryEntryOut,
    MemoryStats,
)
from ..services import memory as memory_service

router = APIRouter(prefix="/memory", tags=["memory"])


def _out(entry) -> MemoryEntryOut:
    return MemoryEntryOut(
        id=entry.id,
        content=entry.content,
        kind=entry.kind,
        scope=entry.scope,
        project_key=entry.project_key,
        source=entry.source,
        pinned=entry.pinned,
        use_count=entry.use_count,
        last_used_at=entry.last_used_at,
        created_at=entry.created_at,
    )


@router.get("", response_model=list[MemoryEntryOut], summary="List remembered entries")
def list_memory(
    scope: str | None = Query(default=None, description="global or project."),
    kind: str | None = Query(default=None),
    project_path: str | None = Query(
        default=None, description="Include this project's entries alongside the global ones."
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[MemoryEntryOut]:
    entries = memory_service.list_entries(
        session, scope=scope, kind=kind, project=project_path, limit=limit
    )
    return [_out(entry) for entry in entries]


@router.post("", response_model=MemoryEntryOut, summary="Remember something")
def add_memory(
    request: MemoryCreateRequest,
    session: Session = Depends(get_session),
) -> MemoryEntryOut:
    try:
        entry = memory_service.remember(
            session,
            request.content,
            kind=request.kind,
            scope=request.scope,
            project=request.project_path,
            source="manual",
            pinned=request.pinned,
        )
    except ValueError as error:
        raise ValidationFailedError(str(error)) from None
    return _out(entry)


@router.get("/stats", response_model=MemoryStats, summary="What is remembered, and what gets used")
def memory_stats(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MemoryStats:
    data = memory_service.stats(session)
    return MemoryStats(enabled=settings.memory_enabled, **data)


@router.delete("/{entry_id}", response_model=MemoryDeleteResponse, summary="Forget one entry")
def forget_memory(
    entry_id: str,
    session: Session = Depends(get_session),
) -> MemoryDeleteResponse:
    if not memory_service.forget(session, entry_id):
        raise NotFoundError(f"Memory entry {entry_id} does not exist.")
    return MemoryDeleteResponse(forgotten=True, id=entry_id)
