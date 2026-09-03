"""Hugging Face Transformers backend with streaming and optional LoRA adapters.

Nothing is imported at module scope: a machine without torch can still start
the server, browse the UI and use the mock backend.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...errors import BackendUnavailableError, BreadError
from .base import BackendStatus, ChatTurn, GenerationParams, InferenceBackend, StopSignal

DTYPE_ALIASES = {
    "bfloat16": "bfloat16",
    "bf16": "bfloat16",
    "float16": "float16",
    "fp16": "float16",
    "half": "float16",
    "float32": "float32",
    "fp32": "float32",
    "auto": "auto",
}


class TransformersBackend(InferenceBackend):
    name = "transformers"

    def __init__(
        self,
        model_id: str,
        tokenizer_id: str | None = None,
        *,
        device: str = "auto",
        dtype: str = "bfloat16",
        quantization_mode: str = "4bit",
        adapter_path: str | None = None,
        context_length: int = 8192,
        trust_remote_code: bool = False,
        allow_download: bool = False,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id or model_id
        self.device = device
        self.dtype = dtype
        self.quantization_mode = quantization_mode
        self.adapter_path = adapter_path or None
        self.context_length = context_length
        self.trust_remote_code = trust_remote_code
        self.allow_download = allow_download
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            started = time.perf_counter()
            torch, transformers = _import_stack()

            tokenizer_kwargs: dict[str, Any] = {
                "trust_remote_code": self.trust_remote_code,
                "local_files_only": not self.allow_download,
            }
            model_kwargs: dict[str, Any] = {
                "trust_remote_code": self.trust_remote_code,
                "local_files_only": not self.allow_download,
            }

            if self.quantization_mode in {"4bit", "8bit"}:
                model_kwargs["quantization_config"] = _quantization_config(
                    self.quantization_mode, self.dtype, torch, transformers
                )
            else:
                model_kwargs["torch_dtype"] = _resolve_dtype(self.dtype, torch)

            model_kwargs["device_map"] = "auto" if self.device == "auto" else self.device

            try:
                self._tokenizer = transformers.AutoTokenizer.from_pretrained(
                    self.tokenizer_id, **tokenizer_kwargs
                )
                self._model = transformers.AutoModelForCausalLM.from_pretrained(
                    self.model_id, **model_kwargs
                )
            except OSError as exc:
                self._model = None
                self._tokenizer = None
                raise _missing_weights_error(self.model_id, self.allow_download, exc) from exc

            if self.adapter_path:
                self._attach_adapter()

            if self._tokenizer.pad_token_id is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            self._model.eval()
            self.loaded_at = datetime.now(timezone.utc)
            self.load_seconds = round(time.perf_counter() - started, 2)

    def _attach_adapter(self) -> None:
        adapter = Path(self.adapter_path or "")
        if not adapter.exists():
            raise BreadError(
                f"Adapter path {adapter} does not exist.",
                code="adapter_not_found",
                hint="Point ADAPTER_PATH at the directory a training run wrote, the "
                "one containing adapter_config.json.",
            )
        try:
            from peft import PeftModel
        except ImportError as exc:  # pragma: no cover - depends on the host env
            raise BackendUnavailableError(
                "peft is not installed, so the LoRA adapter cannot be applied.",
                hint="pip install peft",
            ) from exc
        self._model = PeftModel.from_pretrained(self._model, str(adapter))

    # ---------------------------------------------------------------- unload
    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._tokenizer = None
            self.loaded_at = None
            self.load_seconds = None
            try:
                import gc

                import torch

                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    # ---------------------------------------------------------------- status
    def status(self) -> BackendStatus:
        allocated_mb = None
        try:
            import torch

            if torch.cuda.is_available():
                allocated_mb = round(torch.cuda.memory_allocated() / (1024**2), 1)
        except ImportError:
            pass
        return BackendStatus(
            loaded=self._model is not None,
            backend=self.name,
            model_id=self.model_id,
            tokenizer_id=self.tokenizer_id,
            adapter_path=self.adapter_path,
            quantization_mode=self.quantization_mode,
            dtype=self.dtype,
            device=self.device,
            context_length=self.context_length,
            loaded_at=self.loaded_at,
            load_seconds=self.load_seconds,
            vram_allocated_mb=allocated_mb,
        )

    # ---------------------------------------------------------------- stream
    def stream(
        self,
        turns: list[ChatTurn],
        params: GenerationParams,
        stop_signal: StopSignal | None = None,
    ) -> Iterator[str]:
        if self._model is None:
            self.load()
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

        prompt = self._render_prompt(turns)
        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max(256, self.context_length - params.max_new_tokens),
        )
        inputs = {key: value.to(self._model.device) for key, value in inputs.items()}

        streamer = TextIteratorStreamer(
            self._tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        class _Cancelled(StoppingCriteria):
            def __call__(self, *_: Any, **__: Any) -> bool:
                return stop_signal is not None and stop_signal.stopped

        generate_kwargs: dict[str, Any] = {
            **inputs,
            "streamer": streamer,
            "max_new_tokens": params.max_new_tokens,
            "do_sample": params.temperature > 0,
            "temperature": max(params.temperature, 1e-4),
            "top_p": params.top_p,
            "repetition_penalty": params.repetition_penalty,
            "pad_token_id": self._tokenizer.pad_token_id,
            "stopping_criteria": StoppingCriteriaList([_Cancelled()]),
        }

        errors: list[BaseException] = []

        def _run() -> None:
            try:
                with torch.inference_mode():
                    self._model.generate(**generate_kwargs)
            except BaseException as exc:  # noqa: BLE001 - surfaced to the caller below
                errors.append(exc)
            finally:
                streamer.end()

        worker = threading.Thread(target=_run, name="bread-generate", daemon=True)
        worker.start()

        for delta in streamer:
            if stop_signal is not None and stop_signal.stopped:
                break
            if delta:
                yield delta

        worker.join(timeout=5)
        if errors:
            raise BreadError(
                f"Generation failed: {errors[0]}",
                code="generation_failed",
                status_code=500,
            )

    def _render_prompt(self, turns: list[ChatTurn]) -> str:
        messages = [turn.as_dict() for turn in turns]
        template = getattr(self._tokenizer, "chat_template", None)
        if template:
            return self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        # Plain fallback for base models that ship no chat template.
        rendered = []
        for message in messages:
            rendered.append(f"### {message['role'].capitalize()}\n{message['content']}")
        rendered.append("### Assistant\n")
        return "\n\n".join(rendered)

    def count_tokens(self, text: str) -> int:
        if self._tokenizer is None:
            return super().count_tokens(text)
        return len(self._tokenizer.encode(text))


def _import_stack() -> tuple[Any, Any]:
    try:
        import torch
        import transformers
    except ImportError as exc:  # pragma: no cover - depends on the host env
        raise BackendUnavailableError(
            "PyTorch and Transformers are required for the 'transformers' backend.",
            hint="Install the CUDA build of torch first, then "
            "'pip install -r requirements-train.txt'. See docs/WINDOWS_SETUP.md.",
        ) from exc
    return torch, transformers


def _resolve_dtype(dtype: str, torch: Any) -> Any:
    alias = DTYPE_ALIASES.get(dtype.lower(), "bfloat16")
    if alias == "auto":
        return "auto"
    return getattr(torch, alias)


def _quantization_config(mode: str, compute_dtype: str, torch: Any, transformers: Any) -> Any:
    try:
        import bitsandbytes  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the host env
        raise BackendUnavailableError(
            f"{mode} quantization needs bitsandbytes, which is not installed.",
            hint="pip install bitsandbytes  (on Windows use a build that matches your "
            "CUDA version; see docs/WINDOWS_SETUP.md)",
        ) from exc

    if mode == "8bit":
        return transformers.BitsAndBytesConfig(load_in_8bit=True)
    return transformers.BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=_resolve_dtype(compute_dtype, torch),
    )


def _missing_weights_error(model_id: str, allow_download: bool, exc: OSError) -> BreadError:
    if not allow_download:
        return BackendUnavailableError(
            f"'{model_id}' is not in the local Hugging Face cache.",
            hint="Bread will not start a multi-gigabyte download on its own. Either "
            "run 'python scripts/download_model.py --model-id "
            f"{model_id} --accept-download', or send confirm_download=true to "
            "POST /api/models/load.",
            details={"model_id": model_id, "original_error": str(exc)},
        )
    return BackendUnavailableError(
        f"Could not load '{model_id}': {exc}",
        hint="Check the model id, your disk space and your Hugging Face access token.",
        details={"model_id": model_id},
    )
