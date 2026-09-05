"""A FastAPI service small enough to read and shaped to grow.

Run it:

    pip install "fastapi>=0.110" "uvicorn[standard]" "pydantic>=2"
    uvicorn app:api --reload --host 127.0.0.1 --port 8000

Then open http://127.0.0.1:8000/docs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    """What a caller may send. Validation lives here, not in the handler."""

    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=10_000)


class Note(NoteIn):
    id: int
    created_at: datetime


class NotePage(BaseModel):
    items: list[Note]
    total: int
    limit: int
    offset: int


class NoteStore:
    """Stands in for a database. Swapping it out is why it is a dependency."""

    def __init__(self) -> None:
        self._notes: dict[int, Note] = {}
        self._next_id = 1

    def add(self, payload: NoteIn) -> Note:
        note = Note(id=self._next_id, created_at=datetime.now(UTC), **payload.model_dump())
        self._notes[note.id] = note
        self._next_id += 1
        return note

    def get(self, note_id: int) -> Note | None:
        return self._notes.get(note_id)

    def list(self, *, limit: int, offset: int) -> tuple[list[Note], int]:
        ordered = sorted(self._notes.values(), key=lambda note: note.id)
        return ordered[offset : offset + limit], len(ordered)

    def delete(self, note_id: int) -> bool:
        return self._notes.pop(note_id, None) is not None


store = NoteStore()


def get_store() -> NoteStore:
    """One seam for the whole app: tests override this instead of patching."""

    return store


router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=NotePage, summary="List notes")
def list_notes(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    notes: NoteStore = Depends(get_store),
) -> NotePage:
    # Every list endpoint is paginated from the first commit. Retrofitting
    # pagination onto a client that expects a bare array is a breaking change.
    items, total = notes.list(limit=limit, offset=offset)
    return NotePage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=Note, status_code=status.HTTP_201_CREATED, summary="Create a note")
def create_note(payload: NoteIn, notes: NoteStore = Depends(get_store)) -> Note:
    return notes.add(payload)


@router.get("/{note_id}", response_model=Note, summary="Fetch one note")
def read_note(note_id: int, notes: NoteStore = Depends(get_store)) -> Note:
    note = notes.get(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"No note with id {note_id}.")
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note")
def delete_note(note_id: int, notes: NoteStore = Depends(get_store)) -> None:
    if not notes.delete(note_id):
        raise HTTPException(status_code=404, detail=f"No note with id {note_id}.")


def create_app() -> FastAPI:
    """A factory, so tests build a fresh app instead of importing a global one."""

    api = FastAPI(title="Notes", version="1.0.0")
    api.include_router(router)

    @api.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return api


api = create_app()
