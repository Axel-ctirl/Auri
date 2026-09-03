"""Pydantic request/response models for every Bread endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["system", "user", "assistant"]


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


# ------------------------------------------------------------------ health
class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str
    time: datetime


class GpuDevice(BaseModel):
    index: int
    name: str
    total_memory_mb: Optional[float] = None
    allocated_memory_mb: Optional[float] = None
    reserved_memory_mb: Optional[float] = None
    free_memory_mb: Optional[float] = None
    capability: Optional[str] = None


class GpuStatus(BaseModel):
    cuda_available: bool
    torch_installed: bool
    torch_version: Optional[str] = None
    cuda_version: Optional[str] = None
    driver_version: Optional[str] = None
    device_count: int = 0
    devices: list[GpuDevice] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SystemStatus(BaseModel):
    app: str
    version: str
    python_version: str
    platform: str
    host: str
    port: int
    binds_to_lan: bool
    api_key_required: bool
    data_dir: str
    database_url: str
    rag_enabled: bool
    model: "ModelStatus"
    gpu: GpuStatus
    optional_dependencies: dict[str, bool]
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- models
class ModelSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    model_id: str
    backend: str
    quantization_mode: str
    dtype: str
    device: str
    adapter_path: Optional[str] = None
    context_length: int
    notes: Optional[str] = None
    is_builtin: bool


class ModelRegisterRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=300)
    backend: Literal["mock", "transformers", "llama_cpp", "openai_compat"] = "transformers"
    tokenizer_id: Optional[str] = None
    quantization_mode: Literal["none", "8bit", "4bit"] = "4bit"
    dtype: str = "bfloat16"
    device: str = "auto"
    adapter_path: Optional[str] = None
    gguf_path: Optional[str] = None
    base_url: Optional[str] = None
    context_length: int = Field(default=8192, ge=512, le=1_048_576)
    notes: Optional[str] = None


class ModelLoadRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str] = None
    backend: Optional[Literal["mock", "transformers", "llama_cpp", "openai_compat"]] = None
    quantization_mode: Optional[Literal["none", "8bit", "4bit"]] = None
    dtype: Optional[str] = None
    device: Optional[str] = None
    adapter_path: Optional[str] = None
    gguf_path: Optional[str] = None
    base_url: Optional[str] = None
    confirm_download: bool = Field(
        default=False,
        description="Required before Bread may fetch weights that are not already "
        "in the local Hugging Face cache. Multi-gigabyte downloads never start "
        "without it.",
    )


class ModelStatus(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    loaded: bool
    backend: str
    model_id: Optional[str] = None
    tokenizer_id: Optional[str] = None
    adapter_path: Optional[str] = None
    quantization_mode: Optional[str] = None
    dtype: Optional[str] = None
    device: Optional[str] = None
    context_length: Optional[int] = None
    loaded_at: Optional[datetime] = None
    load_seconds: Optional[float] = None
    vram_allocated_mb: Optional[float] = None
    detail: Optional[str] = None


# --------------------------------------------------------------- chat types
class ChatMessageIn(BaseModel):
    role: Role = "user"
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    conversation_id: Optional[str] = None
    message: str = Field(min_length=1)
    messages: Optional[list[ChatMessageIn]] = Field(
        default=None,
        description="Optional explicit history. When omitted Bread loads the stored "
        "conversation from SQLite.",
    )
    system_prompt: Optional[str] = None
    model_id: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_new_tokens: Optional[int] = Field(default=None, ge=1, le=32768)
    repetition_penalty: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    rag_enabled: Optional[bool] = None
    knowledge_space_id: Optional[str] = None
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=50)
    preset: Optional[str] = Field(
        default=None, description="Name of a prompt preset under prompts/presets/."
    )
    persist: bool = True


class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    chunk_index: int
    score: float
    excerpt: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    conversation_id: str
    message_id: str
    content: str
    model_id: str
    backend: str
    sources: list[Citation] = Field(default_factory=list)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: int = 0
    stopped_early: bool = False


class ChatStopRequest(BaseModel):
    conversation_id: Optional[str] = None
    stream_id: Optional[str] = None


class ChatStopResponse(BaseModel):
    stopped: bool
    stream_ids: list[str] = Field(default_factory=list)


# ------------------------------------------------------------ conversations
class MessageOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    conversation_id: str
    role: Role
    content: str
    sources: list[Citation] = Field(default_factory=list)
    model_id: Optional[str] = None
    token_count: Optional[int] = None
    latency_ms: Optional[int] = None
    stopped_early: bool = False
    error: Optional[str] = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    title: str
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_new_tokens: Optional[int] = None
    rag_enabled: bool = False
    knowledge_space_id: Optional[str] = None
    pinned: bool = False
    archived: bool = False
    message_count: int = 0
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    rag_enabled: bool = False
    knowledge_space_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_new_tokens: Optional[int] = Field(default=None, ge=1, le=32768)
    rag_enabled: Optional[bool] = None
    knowledge_space_id: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


# --------------------------------------------------------- knowledge spaces
class KnowledgeSpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    chunk_size: Optional[int] = Field(default=None, ge=100, le=8000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2000)


class KnowledgeSpaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    chunk_size: Optional[int] = Field(default=None, ge=100, le=8000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2000)


class KnowledgeSpaceOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    embedding_model_id: str
    chunk_size: int
    chunk_overlap: int
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------- documents
class DocumentOut(BaseModel):
    id: str
    knowledge_space_id: str
    filename: str
    extension: str
    size_bytes: int
    content_hash: str
    language: Optional[str] = None
    status: str
    chunk_count: int
    error: Optional[str] = None
    created_at: datetime
    indexed_at: Optional[datetime] = None


class DocumentUploadResponse(BaseModel):
    documents: list[DocumentOut]
    skipped: list[dict[str, str]] = Field(default_factory=list)


class DocumentIndexRequest(BaseModel):
    knowledge_space_id: Optional[str] = None
    document_ids: Optional[list[str]] = None
    force: bool = False


class DocumentIndexResponse(BaseModel):
    indexed_documents: int
    created_chunks: int
    skipped_documents: int
    failed: list[dict[str, str]] = Field(default_factory=list)
    embedding_model_id: str
    duration_ms: int


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    knowledge_space_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
    rerank: Optional[bool] = None


class RagSearchResponse(BaseModel):
    query: str
    knowledge_space_id: Optional[str]
    results: list[Citation]
    embedding_model_id: str
    reranked: bool = False


# --------------------------------------------------------------- datasets
class DatasetRunOut(BaseModel):
    id: str
    name: str
    kind: str
    source: str
    output_path: str
    record_count: int
    accepted_terms: bool
    terms_url: Optional[str] = None
    license_summary: Optional[str] = None
    manifest_json: Optional[str] = None
    status: str
    error: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class DatasetCollectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: Literal[
        "local_code",
        "local_english",
        "codesearchnet",
        "the_stack",
        "fineweb_edu",
        "openwebtext",
        "huggingface",
    ] = "local_code"
    input_paths: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    max_records: int = Field(default=2000, ge=1, le=1_000_000)
    max_file_bytes: int = Field(default=512 * 1024, ge=1024)
    hf_dataset: Optional[str] = None
    hf_config: Optional[str] = None
    hf_split: str = "train"
    allow_licenses: list[str] = Field(default_factory=list)
    accept_terms: bool = Field(
        default=False,
        description="Must be true before Bread downloads anything from an external "
        "dataset host. Local folders never need it.",
    )
    scan_secrets: bool = True
    dedupe: bool = True


class DatasetValidateRequest(BaseModel):
    path: str
    schema_name: Literal["sft_chat", "sft_instruction", "raw_text"] = "sft_chat"
    max_records: Optional[int] = Field(default=None, ge=1)


class DatasetValidationIssue(BaseModel):
    line: int
    field: Optional[str] = None
    problem: str


class DatasetValidateResponse(BaseModel):
    path: str
    total_records: int
    valid_records: int
    invalid_records: int
    issues: list[DatasetValidationIssue] = Field(default_factory=list)
    duplicate_records: int = 0
    secret_hits: int = 0


class DatasetReportResponse(BaseModel):
    path: str
    total_records: int
    total_characters: int
    approx_tokens: int
    language_counts: dict[str, int] = Field(default_factory=dict)
    license_counts: dict[str, int] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)
    length_percentiles: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------- training
class TrainingStartRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config_path: str = Field(
        description="Path to a YAML file under configs/training/, relative to the "
        "repository root."
    )
    dataset_path: Optional[str] = None
    base_model_id: Optional[str] = None
    method: Literal["qlora", "lora", "tiny_scratch"] = "qlora"
    dry_run: bool = Field(
        default=False,
        description="Validate the config, dataset and GPU without launching a run.",
    )


class TrainingRunOut(BaseModel):
    id: str
    name: str
    method: str
    base_model_id: str
    dataset_path: str
    config_path: str
    output_dir: str
    status: str
    pid: Optional[int] = None
    current_step: int
    total_steps: Optional[int] = None
    train_loss: Optional[float] = None
    eval_loss: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class TrainingLogsResponse(BaseModel):
    run_id: str
    lines: list[str]
    truncated: bool = False


class TrainingStopRequest(BaseModel):
    run_id: str


# ---------------------------------------------------------------- settings
class SettingsOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    tokenizer_id: str
    model_backend: str
    model_device: str
    model_dtype: str
    quantization_mode: str
    max_context_length: int
    max_new_tokens: int
    temperature: float
    top_p: float
    repetition_penalty: float
    adapter_path: str
    system_prompt_path: str
    embedding_model_id: str
    rag_enabled: bool
    rag_top_k: int
    rag_rerank_enabled: bool
    chunk_size: int
    chunk_overlap: int
    vector_backend: str
    host: str
    port: int
    require_api_key: bool
    allow_model_download: bool
    max_upload_bytes: int
    data_dir: str


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    repetition_penalty: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    max_new_tokens: Optional[int] = Field(default=None, ge=1, le=32768)
    max_context_length: Optional[int] = Field(default=None, ge=512, le=1_048_576)
    rag_enabled: Optional[bool] = None
    rag_top_k: Optional[int] = Field(default=None, ge=1, le=50)
    rag_rerank_enabled: Optional[bool] = None
    chunk_size: Optional[int] = Field(default=None, ge=100, le=8000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2000)
    allow_model_download: Optional[bool] = None
    system_prompt_path: Optional[str] = None


# ---------------------------------------------------------------- api keys
class ApiKeyCreate(BaseModel):
    label: str = Field(default="local", max_length=120)
    scopes: str = Field(default="read,write")


class ApiKeyOut(BaseModel):
    id: str
    label: str
    key_prefix: str
    scopes: str
    revoked: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown exactly once. Bread stores only its hash.")


class PromptPreset(BaseModel):
    name: str
    title: str
    description: str
    body: str


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


SystemStatus.model_rebuild()
