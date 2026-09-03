"""Backend that talks to an OpenAI-compatible server running on this machine.

Works with llama.cpp's ``llama-server``, vLLM's OpenAI server, LM Studio and
Ollama's compatibility endpoint. Bread only points at hosts you configure; the
default is ``127.0.0.1``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from ...errors import BackendUnavailableError, BreadError
from .base import (
    BackendStatus,
    ChatTurn,
    GenerationParams,
    InferenceBackend,
    StopSignal,
)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


class OpenAICompatBackend(InferenceBackend):
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "not-needed",
        context_length: int = 8192,
        timeout_seconds: float = 300.0,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.context_length = context_length
        self.timeout_seconds = timeout_seconds
        self._reachable = False

    @property
    def is_local(self) -> bool:
        return (urlparse(self.base_url).hostname or "") in LOCAL_HOSTS

    def load(self) -> None:
        try:
            response = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(
                f"No OpenAI-compatible server answered at {self.base_url}.",
                hint="Start your local inference server first, for example "
                "'llama-server -m model.gguf --port 8080', then retry the load.",
                details={"base_url": self.base_url, "original_error": str(exc)},
            ) from exc
        self._reachable = True
        self.loaded_at = datetime.now(UTC)
        self.load_seconds = 0.0
        if not self.model:
            payload = response.json()
            entries = payload.get("data") or []
            if entries:
                self.model = entries[0].get("id", "")

    def unload(self) -> None:
        # The weights live in the other process; Bread only drops its handle.
        self._reachable = False
        self.loaded_at = None

    def status(self) -> BackendStatus:
        return BackendStatus(
            loaded=self._reachable,
            backend=self.name,
            model_id=self.model or None,
            device="remote-process",
            context_length=self.context_length,
            loaded_at=self.loaded_at,
            load_seconds=self.load_seconds,
            detail=f"{self.base_url}"
            + ("" if self.is_local else "  (WARNING: this endpoint is not on localhost)"),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def stream(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> Iterator[str]:
        if not self._reachable:
            self.load()
        body = {
            "model": self.model,
            "messages": [turn.as_dict() for turn in turns],
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_new_tokens,
            "stream": True,
        }
        if params.stop:
            body["stop"] = params.stop

        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
                timeout=self.timeout_seconds,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if stop_signal is not None and stop_signal.stopped:
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    piece = (choices[0].get("delta") or {}).get("content")
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise BreadError(
                f"The inference server at {self.base_url} failed mid-stream: {exc}",
                code="upstream_stream_failed",
                status_code=502,
            ) from exc
