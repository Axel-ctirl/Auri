"""Process-wide model registry.

Exactly one backend is live at a time. The registry also tracks in-flight
streams so ``POST /api/chat/stop`` can cancel them.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from ...config import Settings, get_settings
from ...errors import BreadError
from .base import BackendStatus, InferenceBackend, StopSignal
from .llamacpp_backend import LlamaCppBackend
from .mock_backend import MockBackend
from .openai_compat_backend import OpenAICompatBackend
from .transformers_backend import TransformersBackend

BACKEND_NAMES = ("mock", "transformers", "llama_cpp", "openai_compat")


def build_backend(settings: Settings, overrides: dict[str, Any] | None = None) -> InferenceBackend:
    """Instantiate a backend from settings plus per-request overrides."""

    overrides = {key: value for key, value in (overrides or {}).items() if value is not None}
    backend_name = overrides.get("backend", settings.model_backend)

    if backend_name == "mock":
        return MockBackend(delay_seconds=settings.mock_delay_seconds)

    if backend_name == "transformers":
        return TransformersBackend(
            model_id=overrides.get("model_id", settings.model_id),
            tokenizer_id=overrides.get("tokenizer_id", settings.resolved_tokenizer_id),
            device=overrides.get("device", settings.model_device),
            dtype=overrides.get("dtype", settings.model_dtype),
            quantization_mode=overrides.get("quantization_mode", settings.quantization_mode),
            adapter_path=overrides.get("adapter_path", settings.adapter_path),
            context_length=overrides.get("context_length", settings.max_context_length),
            trust_remote_code=settings.trust_remote_code,
            allow_download=bool(
                overrides.get("confirm_download", False) or settings.allow_model_download
            ),
        )

    if backend_name == "llama_cpp":
        return LlamaCppBackend(
            gguf_path=overrides.get("gguf_path", settings.gguf_model_path),
            context_length=overrides.get("context_length", settings.max_context_length),
            n_gpu_layers=overrides.get("n_gpu_layers", settings.gguf_n_gpu_layers),
        )

    if backend_name == "openai_compat":
        return OpenAICompatBackend(
            base_url=overrides.get("base_url", settings.openai_compat_base_url),
            model=overrides.get("model_id", settings.openai_compat_model or settings.model_id),
            api_key=settings.openai_compat_api_key,
            context_length=overrides.get("context_length", settings.max_context_length),
        )

    raise BreadError(
        f"Unknown model backend '{backend_name}'.",
        code="unknown_backend",
        hint=f"Pick one of: {', '.join(BACKEND_NAMES)}.",
    )


class ModelRegistry:
    def __init__(self) -> None:
        self._backend: InferenceBackend | None = None
        self._lock = threading.RLock()
        self._streams: dict[str, StopSignal] = {}
        self._stream_conversations: dict[str, str] = {}

    # -------------------------------------------------------------- lifecycle
    def load(self, settings: Settings, overrides: dict[str, Any] | None = None) -> BackendStatus:
        with self._lock:
            if self._backend is not None:
                self._backend.unload()
            backend = build_backend(settings, overrides)
            backend.load()
            self._backend = backend
            return backend.status()

    def unload(self) -> BackendStatus:
        with self._lock:
            if self._backend is None:
                return BackendStatus(loaded=False, backend="none", detail="Nothing was loaded.")
            status = self._backend.status()
            self._backend.unload()
            self._backend = None
            return BackendStatus(
                loaded=False,
                backend=status.backend,
                model_id=status.model_id,
                detail="Unloaded. VRAM is released once Python's allocator returns it.",
            )

    def status(self) -> BackendStatus:
        with self._lock:
            if self._backend is None:
                return BackendStatus(
                    loaded=False,
                    backend="none",
                    detail="No model is loaded. POST /api/models/load to bring one up.",
                )
            return self._backend.status()

    def get_or_autoload(self, settings: Settings | None = None) -> InferenceBackend:
        """Return the live backend, auto-loading cheap backends on first use.

        The mock backend loads instantly, so making the user press a button for
        it would be pointless. Real backends must be loaded explicitly, which
        keeps a stray chat request from triggering a huge download or a long
        model load the caller did not ask for.
        """

        settings = settings or get_settings()
        with self._lock:
            if self._backend is not None:
                return self._backend
            if settings.model_backend == "mock":
                backend = build_backend(settings)
                backend.load()
                self._backend = backend
                return backend
        raise BreadError(
            "No model is loaded.",
            code="model_not_loaded",
            status_code=409,
            hint="Open the Models page and press Load, or POST /api/models/load.",
        )

    # ----------------------------------------------------------------- streams
    def register_stream(self, conversation_id: str | None = None) -> tuple[str, StopSignal]:
        stream_id = uuid.uuid4().hex
        signal = StopSignal()
        with self._lock:
            self._streams[stream_id] = signal
            if conversation_id:
                self._stream_conversations[stream_id] = conversation_id
        return stream_id, signal

    def release_stream(self, stream_id: str) -> None:
        with self._lock:
            self._streams.pop(stream_id, None)
            self._stream_conversations.pop(stream_id, None)

    def stop_stream(self, stream_id: str) -> bool:
        with self._lock:
            signal = self._streams.get(stream_id)
        if signal is None:
            return False
        signal.stop()
        return True

    def stop_conversation(self, conversation_id: str) -> list[str]:
        with self._lock:
            matches = [
                stream_id
                for stream_id, convo in self._stream_conversations.items()
                if convo == conversation_id
            ]
            signals = [self._streams[sid] for sid in matches if sid in self._streams]
        for signal in signals:
            signal.stop()
        return matches

    def stop_all(self) -> list[str]:
        with self._lock:
            matches = list(self._streams)
            signals = list(self._streams.values())
        for signal in signals:
            signal.stop()
        return matches

    def active_stream_ids(self) -> list[str]:
        with self._lock:
            return list(self._streams)


registry = ModelRegistry()
