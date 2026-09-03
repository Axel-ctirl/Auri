"""Reading and updating runtime settings.

Updates are written to the ``settings`` table and applied to the live settings
object, so they survive a restart without editing ``.env``. Fields that decide
how the process is exposed to the network (host, port, API-key enforcement) are
deliberately not editable over HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..audit import record_action
from ..config import Settings, get_settings
from ..db import get_session, read_setting, write_setting
from ..schemas import SettingsOut, SettingsUpdate

router = APIRouter(tags=["settings"])

SETTINGS_KEY = "runtime_overrides"


def apply_persisted_overrides(session: Session, settings: Settings) -> None:
    """Re-apply saved overrides onto a freshly constructed settings object."""

    overrides = read_setting(session, SETTINGS_KEY, default={}) or {}
    editable = set(SettingsUpdate.model_fields)
    for key, value in overrides.items():
        if key in editable and value is not None:
            setattr(settings, key, value)


def _serialize(settings: Settings) -> SettingsOut:
    return SettingsOut(
        model_id=settings.model_id,
        tokenizer_id=settings.resolved_tokenizer_id,
        model_backend=settings.model_backend,
        model_device=settings.model_device,
        model_dtype=settings.model_dtype,
        quantization_mode=settings.quantization_mode,
        max_context_length=settings.max_context_length,
        max_new_tokens=settings.max_new_tokens,
        temperature=settings.temperature,
        top_p=settings.top_p,
        repetition_penalty=settings.repetition_penalty,
        adapter_path=settings.adapter_path,
        system_prompt_path=settings.system_prompt_path,
        embedding_model_id=settings.embedding_model_id,
        rag_enabled=settings.rag_enabled,
        rag_top_k=settings.rag_top_k,
        rag_rerank_enabled=settings.rag_rerank_enabled,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        vector_backend=settings.vector_backend,
        host=settings.host,
        port=settings.port,
        require_api_key=settings.require_api_key or settings.binds_to_lan,
        allow_model_download=settings.allow_model_download,
        max_upload_bytes=settings.max_upload_bytes,
        data_dir=str(settings.data_dir),
    )


@router.get("/settings", response_model=SettingsOut, summary="Current effective settings")
def get_runtime_settings(settings: Settings = Depends(get_settings)) -> SettingsOut:
    return _serialize(settings)


@router.patch("/settings", response_model=SettingsOut, summary="Update runtime settings")
def update_runtime_settings(
    payload: SettingsUpdate,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SettingsOut:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        stored = read_setting(session, SETTINGS_KEY, default={}) or {}
        stored.update(changes)
        write_setting(session, SETTINGS_KEY, stored)
        session.commit()
        for key, value in changes.items():
            setattr(settings, key, value)
        record_action(session, "settings.update", detail=changes)
    return _serialize(settings)
