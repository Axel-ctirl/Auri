"""SQLModel tables backing Bread's local SQLite database.

Everything Bread stores lives in one SQLite file under ``data/``. There is no
remote database, no analytics sink, and no background upload.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, Index, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex


class LocalProfile(SQLModel, table=True):
    """A local persona. Bread is single-user by default but keeps the seam open."""

    __tablename__ = "local_profiles"

    id: str = Field(default_factory=new_id, primary_key=True)
    display_name: str = Field(default="local")
    is_default: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(default_factory=new_id, primary_key=True)
    title: str = Field(default="New chat", index=True)
    profile_id: str | None = Field(default=None, foreign_key="local_profiles.id")
    model_id: str | None = Field(default=None)
    system_prompt: str | None = Field(default=None, sa_column=Column(Text))
    temperature: float | None = Field(default=None)
    max_new_tokens: int | None = Field(default=None)
    top_p: float | None = Field(default=None)
    rag_enabled: bool = Field(default=False)
    knowledge_space_id: str | None = Field(default=None, foreign_key="knowledge_spaces.id")
    pinned: bool = Field(default=False)
    archived: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id", index=True)
    role: str = Field(default="user")  # system | user | assistant
    content: str = Field(default="", sa_column=Column(Text))
    # JSON-encoded list of citation dicts produced by the RAG retriever.
    sources_json: str | None = Field(default=None, sa_column=Column(Text))
    model_id: str | None = Field(default=None)
    token_count: int | None = Field(default=None)
    latency_ms: int | None = Field(default=None)
    stopped_early: bool = Field(default=False)
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class SettingRecord(SQLModel, table=True):
    """Operator-editable overrides that survive a restart."""

    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value_json: str = Field(default="null", sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=utcnow)


class ModelRecord(SQLModel, table=True):
    __tablename__ = "models"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    model_id: str = Field(default="")
    tokenizer_id: str | None = Field(default=None)
    backend: str = Field(default="mock")
    quantization_mode: str = Field(default="none")
    dtype: str = Field(default="bfloat16")
    device: str = Field(default="auto")
    adapter_path: str | None = Field(default=None)
    gguf_path: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    context_length: int = Field(default=8192)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    is_builtin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


class KnowledgeSpace(SQLModel, table=True):
    __tablename__ = "knowledge_spaces"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    description: str | None = Field(default=None, sa_column=Column(Text))
    embedding_model_id: str = Field(default="")
    chunk_size: int = Field(default=900)
    chunk_overlap: int = Field(default=150)
    document_count: int = Field(default=0)
    chunk_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = Field(default_factory=new_id, primary_key=True)
    knowledge_space_id: str = Field(foreign_key="knowledge_spaces.id", index=True)
    filename: str = Field(default="")
    stored_path: str = Field(default="")
    extension: str = Field(default="")
    media_type: str | None = Field(default=None)
    size_bytes: int = Field(default=0)
    content_hash: str = Field(default="", index=True)
    language: str | None = Field(default=None)
    status: str = Field(default="uploaded")  # uploaded | indexed | failed | skipped
    chunk_count: int = Field(default=0)
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    indexed_at: datetime | None = Field(default=None)


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_chunks_document_index", "document_id", "chunk_index"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    document_id: str = Field(foreign_key="documents.id", index=True)
    knowledge_space_id: str = Field(foreign_key="knowledge_spaces.id", index=True)
    chunk_index: int = Field(default=0)
    content: str = Field(default="", sa_column=Column(Text))
    token_estimate: int = Field(default=0)
    start_line: int | None = Field(default=None)
    end_line: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class DatasetRun(SQLModel, table=True):
    __tablename__ = "dataset_runs"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    kind: str = Field(default="collect")  # collect | clean | dedupe | validate | report
    source: str = Field(default="local")
    output_path: str = Field(default="")
    record_count: int = Field(default=0)
    accepted_terms: bool = Field(default=False)
    terms_url: str | None = Field(default=None)
    license_summary: str | None = Field(default=None, sa_column=Column(Text))
    manifest_json: str | None = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="pending")
    error: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = Field(default=None)


class TrainingRun(SQLModel, table=True):
    __tablename__ = "training_runs"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    method: str = Field(default="qlora")  # qlora | lora | full | tiny_scratch
    base_model_id: str = Field(default="")
    dataset_path: str = Field(default="")
    config_path: str = Field(default="")
    config_json: str | None = Field(default=None, sa_column=Column(Text))
    output_dir: str = Field(default="")
    status: str = Field(default="pending")  # pending|running|completed|failed|stopped
    pid: int | None = Field(default=None)
    current_step: int = Field(default=0)
    total_steps: int | None = Field(default=None)
    train_loss: float | None = Field(default=None)
    eval_loss: float | None = Field(default=None)
    error: str | None = Field(default=None, sa_column=Column(Text))
    log_path: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)


class TrainingCheckpoint(SQLModel, table=True):
    __tablename__ = "training_checkpoints"

    id: str = Field(default_factory=new_id, primary_key=True)
    run_id: str = Field(foreign_key="training_runs.id", index=True)
    step: int = Field(default=0)
    path: str = Field(default="")
    train_loss: float | None = Field(default=None)
    eval_loss: float | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: str = Field(default_factory=new_id, primary_key=True)
    label: str = Field(default="local")
    key_prefix: str = Field(default="", index=True)
    key_hash: str = Field(default="", index=True)
    scopes: str = Field(default="read,write")
    revoked: bool = Field(default=False)
    last_used_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: str = Field(default_factory=new_id, primary_key=True)
    action: str = Field(index=True)
    target_type: str | None = Field(default=None)
    target_id: str | None = Field(default=None)
    actor: str = Field(default="local")
    detail_json: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow, index=True)
