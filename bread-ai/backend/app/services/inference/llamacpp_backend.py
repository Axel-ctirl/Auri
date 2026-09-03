"""GGUF backend built on llama-cpp-python.

Useful when you want a large quantized model on modest VRAM, or when you would
rather not install the full PyTorch stack. The GGUF file must already be on
disk: Bread never downloads one for you.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...errors import BackendUnavailableError, BreadError
from .base import (
    BackendStatus,
    ChatTurn,
    GenerationParams,
    InferenceBackend,
    StopSignal,
)


class LlamaCppBackend(InferenceBackend):
    name = "llama_cpp"

    def __init__(
        self,
        gguf_path: str,
        *,
        context_length: int = 8192,
        n_gpu_layers: int = -1,
        n_threads: int | None = None,
        chat_format: str | None = None,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.gguf_path = gguf_path
        self.context_length = context_length
        self.n_gpu_layers = n_gpu_layers
        self.n_threads = n_threads
        self.chat_format = chat_format
        self._llm: Any = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._llm is not None:
                return
            path = Path(self.gguf_path)
            if not self.gguf_path:
                raise BreadError(
                    "GGUF_MODEL_PATH is empty.",
                    code="gguf_path_missing",
                    hint="Set GGUF_MODEL_PATH in .env to a .gguf file you already have.",
                )
            if not path.exists():
                raise BreadError(
                    f"No GGUF file at {path}.",
                    code="gguf_not_found",
                    hint="Download the .gguf yourself, then point GGUF_MODEL_PATH at it.",
                )
            try:
                from llama_cpp import Llama
            except ImportError as exc:  # pragma: no cover - depends on the host env
                raise BackendUnavailableError(
                    "llama-cpp-python is not installed.",
                    hint="pip install llama-cpp-python  (build with CUDA support for "
                    "GPU offload; see docs/WINDOWS_SETUP.md)",
                ) from exc

            started = time.perf_counter()
            kwargs: dict[str, Any] = {
                "model_path": str(path),
                "n_ctx": self.context_length,
                "n_gpu_layers": self.n_gpu_layers,
                "verbose": False,
            }
            if self.n_threads:
                kwargs["n_threads"] = self.n_threads
            if self.chat_format:
                kwargs["chat_format"] = self.chat_format
            self._llm = Llama(**kwargs)
            self.loaded_at = datetime.now(UTC)
            self.load_seconds = round(time.perf_counter() - started, 2)

    def unload(self) -> None:
        with self._lock:
            self._llm = None
            self.loaded_at = None
            self.load_seconds = None

    def status(self) -> BackendStatus:
        return BackendStatus(
            loaded=self._llm is not None,
            backend=self.name,
            model_id=Path(self.gguf_path).name or None,
            quantization_mode="gguf",
            device=f"gpu_layers={self.n_gpu_layers}",
            context_length=self.context_length,
            loaded_at=self.loaded_at,
            load_seconds=self.load_seconds,
            detail=str(self.gguf_path) or None,
        )

    def stream(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> Iterator[str]:
        if self._llm is None:
            self.load()
        completion = self._llm.create_chat_completion(
            messages=[turn.as_dict() for turn in turns],
            temperature=params.temperature,
            top_p=params.top_p,
            max_tokens=params.max_new_tokens,
            repeat_penalty=params.repetition_penalty,
            stop=params.stop or None,
            stream=True,
        )
        for event in completion:
            if stop_signal is not None and stop_signal.stopped:
                break
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                yield piece

    def count_tokens(self, text: str) -> int:
        if self._llm is None:
            return super().count_tokens(text)
        try:
            return len(self._llm.tokenize(text.encode("utf-8")))
        except Exception:  # pragma: no cover - tokenizer quirks vary by build
            return super().count_tokens(text)
