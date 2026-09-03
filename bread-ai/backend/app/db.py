"""Database engine, session helpers and first-run initialisation."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from .config import Settings, get_settings
from .models import KnowledgeSpace, LocalProfile, ModelRecord, SettingRecord

_engine: Engine | None = None

BUILTIN_MODELS: list[dict[str, Any]] = [
    {
        "name": "Mock (no download)",
        "model_id": "bread/mock",
        "backend": "mock",
        "quantization_mode": "none",
        "context_length": 8192,
        "notes": "Deterministic canned responses. Use it to exercise the UI and the "
        "API without pulling any weights.",
    },
    {
        "name": "Qwen2.5-Coder-7B-Instruct (4-bit)",
        "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "backend": "transformers",
        "quantization_mode": "4bit",
        "context_length": 8192,
        "notes": "Default coding model. Fits comfortably on a 32 GB RTX 5090 and "
        "leaves room for QLoRA training.",
    },
    {
        "name": "Qwen2.5-Coder-14B-Instruct (4-bit)",
        "model_id": "Qwen/Qwen2.5-Coder-14B-Instruct",
        "backend": "transformers",
        "quantization_mode": "4bit",
        "context_length": 8192,
        "notes": "Stronger answers, slower tokens. Still fits in 32 GB at 4-bit.",
    },
    {
        "name": "Qwen2.5-Coder-1.5B-Instruct (bf16)",
        "model_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "backend": "transformers",
        "quantization_mode": "none",
        "context_length": 8192,
        "notes": "Low-VRAM fallback for 8-12 GB cards and for smoke tests.",
    },
    {
        "name": "Local GGUF via llama.cpp",
        "model_id": "local-gguf",
        "backend": "llama_cpp",
        "quantization_mode": "4bit",
        "context_length": 8192,
        "notes": "Point GGUF_MODEL_PATH at a .gguf file you already downloaded.",
    },
    {
        "name": "OpenAI-compatible local server",
        "model_id": "openai-compat",
        "backend": "openai_compat",
        "quantization_mode": "none",
        "context_length": 8192,
        "notes": "Talks to llama-server, vLLM, LM Studio or Ollama on this machine.",
    },
]


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        url = settings.resolved_database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=False, connect_args=connect_args)
        if url.startswith("sqlite"):
            with _engine.connect() as connection:
                # WAL keeps the UI responsive while a long write is in flight.
                connection.execute(text("PRAGMA journal_mode=WAL"))
                connection.execute(text("PRAGMA foreign_keys=ON"))
                connection.commit()
    return _engine


def reset_engine() -> None:
    """Dispose of the cached engine. Used by tests."""

    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db(settings: Settings | None = None) -> None:
    """Create tables and seed the rows a fresh install needs.

    This is deliberately idempotent so ``uvicorn`` can call it on every start.
    Alembic is available for schema changes that cannot be expressed as an
    additive ``create_all`` (see ``docs/ARCHITECTURE.md``).
    """

    settings = settings or get_settings()
    settings.ensure_directories()
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    _apply_additive_migrations(engine)

    with Session(engine) as session:
        if not session.exec(select(LocalProfile)).first():
            session.add(LocalProfile(display_name="local", is_default=True))

        existing_models = {
            record.model_id for record in session.exec(select(ModelRecord)).all()
        }
        for entry in BUILTIN_MODELS:
            if entry["model_id"] in existing_models:
                continue
            session.add(ModelRecord(is_builtin=True, **entry))

        if not session.exec(select(KnowledgeSpace)).first():
            session.add(
                KnowledgeSpace(
                    name="Default",
                    description="Starter knowledge space. Upload code or notes here.",
                    embedding_model_id=settings.embedding_model_id,
                    chunk_size=settings.chunk_size,
                    chunk_overlap=settings.chunk_overlap,
                )
            )
        session.commit()


def _apply_additive_migrations(engine: Engine) -> None:
    """Add columns that newer Bread versions expect on an older SQLite file.

    ``SQLModel.metadata.create_all`` never alters an existing table, so a schema
    that grew a column between releases needs a nudge. Anything more invasive
    than an added nullable column belongs in an Alembic revision.
    """

    inspector = inspect(engine)
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not (column.nullable or column.default is not None):
                continue
            column_type = column.type.compile(engine.dialect)
            with engine.connect() as connection:
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
                )
                connection.commit()


def new_session() -> Session:
    """Open a session that keeps attribute values readable after a commit.

    With the default ``expire_on_commit=True`` every ORM object is expired the
    moment anything commits, and a later ``model_dump()`` on it comes back empty
    because SQLModel reads ``__dict__`` rather than triggering a lazy refresh.
    Bread commits often (audit rows, counters), so the objects a request already
    holds must stay usable.
    """

    return Session(get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a short-lived session."""

    with new_session() as session:
        yield session


def read_setting(session: Session, key: str, default: Any = None) -> Any:
    record = session.get(SettingRecord, key)
    if record is None:
        return default
    try:
        return json.loads(record.value_json)
    except json.JSONDecodeError:
        return default


def write_setting(session: Session, key: str, value: Any) -> None:
    from .models import utcnow

    record = session.get(SettingRecord, key)
    payload = json.dumps(value)
    if record is None:
        session.add(SettingRecord(key=key, value_json=payload))
    else:
        record.value_json = payload
        record.updated_at = utcnow()
        session.add(record)
