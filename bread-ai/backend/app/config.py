"""Runtime configuration for the Bread backend.

Configuration is layered, lowest priority first:

1. The defaults declared on :class:`Settings`.
2. A YAML profile pointed at by ``BREAD_CONFIG_FILE`` (see ``configs/``).
3. Environment variables, including anything in a local ``.env`` file.

Nothing here reaches out to the network. Bread is local-first: the only time
the process touches the internet is when the operator explicitly asks for a
model download or a dataset collection run.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data"

ModelBackend = Literal["mock", "transformers", "llama_cpp", "openai_compat"]
QuantizationMode = Literal["none", "8bit", "4bit"]
VectorBackend = Literal["numpy", "chroma"]


def _yaml_overlay() -> dict[str, Any]:
    """Read the YAML profile named by ``BREAD_CONFIG_FILE``, if any."""

    raw_path = os.environ.get("BREAD_CONFIG_FILE", "").strip()
    if not raw_path:
        return {}

    config_path = Path(raw_path)
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"BREAD_CONFIG_FILE points at {config_path}, which does not exist.")

    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping at the top level.")

    # YAML keys are written in the same UPPER_SNAKE_CASE style as the env vars so
    # that a profile file and a .env file stay readable side by side.
    flattened: dict[str, Any] = {}
    for section_key, section_value in loaded.items():
        if isinstance(section_value, dict):
            flattened.update({str(k): v for k, v in section_value.items()})
        else:
            flattened[str(section_key)] = section_value
    return {key.lower(): value for key, value in flattened.items()}


class Settings(BaseSettings):
    """Everything the running server needs to know."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        protected_namespaces=(),
    )

    # ---------------------------------------------------------------- server
    app_name: str = "Bread"
    app_version: str = "0.1.0"
    host: str = Field(default="127.0.0.1", alias="BREAD_HOST")
    port: int = Field(default=8000, alias="BREAD_PORT")
    log_level: str = Field(default="info", alias="BREAD_LOG_LEVEL")
    data_dir: Path = Field(default=DEFAULT_DATA_DIR, alias="BREAD_DATA_DIR")
    database_url: str = Field(default="", alias="BREAD_DATABASE_URL")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="BREAD_CORS_ORIGINS",
    )

    # -------------------------------------------------------------- security
    require_api_key: bool = Field(default=False, alias="BREAD_REQUIRE_API_KEY")
    allow_lan_binding: bool = Field(default=False, alias="BREAD_ALLOW_LAN_BINDING")
    rate_limit_requests: int = Field(default=120, alias="BREAD_RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, alias="BREAD_RATE_LIMIT_WINDOW")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, alias="BREAD_MAX_UPLOAD_BYTES")

    # ----------------------------------------------------------------- model
    model_id: str = Field(default="Qwen/Qwen2.5-Coder-7B-Instruct", alias="MODEL_ID")
    tokenizer_id: str = Field(default="", alias="TOKENIZER_ID")
    model_backend: ModelBackend = Field(default="mock", alias="MODEL_BACKEND")
    model_device: str = Field(default="auto", alias="MODEL_DEVICE")
    model_dtype: str = Field(default="bfloat16", alias="MODEL_DTYPE")
    quantization_mode: QuantizationMode = Field(default="4bit", alias="QUANTIZATION_MODE")
    max_context_length: int = Field(default=8192, alias="MAX_CONTEXT_LENGTH")
    max_new_tokens: int = Field(default=1024, alias="MAX_NEW_TOKENS")
    temperature: float = Field(default=0.2, alias="TEMPERATURE")
    top_p: float = Field(default=0.95, alias="TOP_P")
    repetition_penalty: float = Field(default=1.05, alias="REPETITION_PENALTY")
    adapter_path: str = Field(default="", alias="ADAPTER_PATH")
    system_prompt_path: str = Field(default="prompts/system_default.md", alias="SYSTEM_PROMPT_PATH")
    trust_remote_code: bool = Field(default=False, alias="TRUST_REMOTE_CODE")
    mock_delay_seconds: float = Field(default=0.01, alias="MOCK_DELAY_SECONDS")
    allow_model_download: bool = Field(default=False, alias="ALLOW_MODEL_DOWNLOAD")

    # llama.cpp / GGUF
    gguf_model_path: str = Field(default="", alias="GGUF_MODEL_PATH")
    gguf_n_gpu_layers: int = Field(default=-1, alias="GGUF_N_GPU_LAYERS")

    # OpenAI-compatible local server (llama-server, vLLM, LM Studio, Ollama, ...)
    openai_compat_base_url: str = Field(
        default="http://127.0.0.1:8080/v1", alias="OPENAI_COMPAT_BASE_URL"
    )
    openai_compat_api_key: str = Field(default="not-needed", alias="OPENAI_COMPAT_API_KEY")
    openai_compat_model: str = Field(default="", alias="OPENAI_COMPAT_MODEL")

    # ------------------------------------------------------------------- RAG
    rag_enabled: bool = Field(default=True, alias="RAG_ENABLED")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_rerank_enabled: bool = Field(default=False, alias="RAG_RERANK_ENABLED")
    rag_rerank_model_id: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RAG_RERANK_MODEL_ID"
    )
    embedding_model_id: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_ID"
    )
    embedding_backend: str = Field(default="auto", alias="EMBEDDING_BACKEND")
    vector_backend: VectorBackend = Field(default="numpy", alias="VECTOR_BACKEND")
    chunk_size: int = Field(default=900, alias="RAG_CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, alias="RAG_CHUNK_OVERLAP")

    # ---------------------------------------------------------------- memory
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_recall_limit: int = Field(default=8, alias="MEMORY_RECALL_LIMIT")
    # Checking a reply's Python for invented APIs costs one extra generation per
    # problem found, so it is opt-in per request rather than always on.
    verify_code_default: bool = Field(default=False, alias="VERIFY_CODE_DEFAULT")
    verify_code_attempts: int = Field(default=3, alias="VERIFY_CODE_ATTEMPTS")

    # -------------------------------------------------------------- training
    training_output_dir: str = Field(default="runs", alias="TRAINING_OUTPUT_DIR")
    datasets_dir: str = Field(default="datasets", alias="DATASETS_DIR")

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: Any) -> Any:
        if not value:
            return DEFAULT_DATA_DIR
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'bread.db').as_posix()}"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def runs_dir(self) -> Path:
        path = Path(self.training_output_dir)
        return path if path.is_absolute() else (self.data_dir / path)

    @property
    def datasets_path(self) -> Path:
        path = Path(self.datasets_dir)
        return path if path.is_absolute() else (self.data_dir / path)

    @property
    def resolved_tokenizer_id(self) -> str:
        return self.tokenizer_id or self.model_id

    @property
    def binds_to_lan(self) -> bool:
        return self.host not in {"127.0.0.1", "localhost", "::1"}

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.uploads_dir,
            self.vector_dir,
            self.runs_dir,
            self.datasets_path,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def system_prompt(self) -> str:
        """Load the system prompt from disk, falling back to a built-in default."""

        path = Path(self.system_prompt_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return (
            "You are Bread, a local-first coding assistant. Answer in professional "
            "English, write correct and readable code, and say plainly when you are "
            "unsure instead of inventing APIs."
        )


def _alias_to_field_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field_name, field in Settings.model_fields.items():
        mapping[field_name.lower()] = field_name
        if field.alias:
            mapping[field.alias.lower()] = field_name
    return mapping


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    alias_map = _alias_to_field_map()
    env_keys = {key.lower() for key in os.environ}
    overlay: dict[str, Any] = {}
    for key, value in _yaml_overlay().items():
        field_name = alias_map.get(key)
        if field_name is None:
            continue
        # A real environment variable always beats the YAML profile, so a shell
        # override works without editing the profile file.
        field = Settings.model_fields[field_name]
        candidate_env_names = {field_name.lower()}
        if field.alias:
            candidate_env_names.add(field.alias.lower())
        if candidate_env_names & env_keys:
            continue
        overlay[field_name] = value
    settings = Settings(**overlay)  # type: ignore[arg-type]
    settings.ensure_directories()
    return settings


def reset_settings_cache() -> None:
    """Drop the cached settings object. Used by tests and by ``/api/settings``."""

    get_settings.cache_clear()
