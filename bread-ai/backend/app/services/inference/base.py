"""Backend-agnostic inference contract.

Every backend yields plain text deltas. The router turns those into
Server-Sent Events, so adding a backend never touches the HTTP layer.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ChatTurn:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class GenerationParams:
    temperature: float = 0.2
    top_p: float = 0.95
    max_new_tokens: int = 1024
    repetition_penalty: float = 1.05
    stop: list[str] = field(default_factory=list)
    seed: int | None = None


class StopSignal:
    """Cooperative cancellation token shared with a running generation."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def stop(self) -> None:
        self._event.set()

    @property
    def stopped(self) -> bool:
        return self._event.is_set()


@dataclass
class BackendStatus:
    loaded: bool
    backend: str
    model_id: str | None = None
    tokenizer_id: str | None = None
    adapter_path: str | None = None
    quantization_mode: str | None = None
    dtype: str | None = None
    device: str | None = None
    context_length: int | None = None
    loaded_at: datetime | None = None
    load_seconds: float | None = None
    vram_allocated_mb: float | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "loaded": self.loaded,
            "backend": self.backend,
            "model_id": self.model_id,
            "tokenizer_id": self.tokenizer_id,
            "adapter_path": self.adapter_path,
            "quantization_mode": self.quantization_mode,
            "dtype": self.dtype,
            "device": self.device,
            "context_length": self.context_length,
            "loaded_at": self.loaded_at,
            "load_seconds": self.load_seconds,
            "vram_allocated_mb": self.vram_allocated_mb,
            "detail": self.detail,
        }


class InferenceBackend(ABC):
    """Common surface implemented by the mock, Transformers, GGUF and HTTP backends."""

    name: str = "base"

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.loaded_at: datetime | None = None
        self.load_seconds: float | None = None

    @abstractmethod
    def load(self) -> None:
        """Bring the model into memory. Must be idempotent."""

    @abstractmethod
    def unload(self) -> None:
        """Release memory. Must be safe to call when nothing is loaded."""

    @abstractmethod
    def status(self) -> BackendStatus: ...

    @abstractmethod
    def stream(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> Iterator[str]:
        """Yield text deltas until the model stops or ``stop_signal`` fires."""

    def generate(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> str:
        return "".join(self.stream(turns, params, stop_signal))

    def count_tokens(self, text: str) -> int:
        """Rough token estimate. Backends with a real tokenizer override this."""

        return max(1, len(text) // 4)
