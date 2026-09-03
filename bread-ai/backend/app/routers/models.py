"""Model catalogue and load/unload control."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..audit import record_action
from ..config import Settings, get_settings
from ..db import get_session
from ..errors import NotFoundError
from ..models import ModelRecord
from ..schemas import (
    ModelLoadRequest,
    ModelRegisterRequest,
    ModelStatus,
    ModelSummary,
)
from ..services.inference import registry

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelSummary], summary="List registered models")
def list_models(session: Session = Depends(get_session)) -> list[ModelSummary]:
    records = session.exec(select(ModelRecord).order_by(ModelRecord.name)).all()
    return [ModelSummary(**record.model_dump()) for record in records]


@router.get("/status", response_model=ModelStatus, summary="What is loaded right now")
def model_status() -> ModelStatus:
    return ModelStatus(**registry.status().as_dict())


@router.post("/load", response_model=ModelStatus, summary="Load a model into memory")
def load_model(
    payload: ModelLoadRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ModelStatus:
    """Bring a backend up.

    Weights that are not already in the local cache are **not** downloaded
    unless ``confirm_download`` is true. That keeps a stray click from pulling
    fifteen gigabytes over a metered connection.
    """

    overrides = payload.model_dump(exclude_none=True)

    # A registered model id resolves to its stored configuration.
    if payload.model_id:
        record = session.exec(
            select(ModelRecord).where(ModelRecord.model_id == payload.model_id)
        ).first()
        if record is not None:
            overrides.setdefault("backend", record.backend)
            overrides.setdefault("quantization_mode", record.quantization_mode)
            overrides.setdefault("dtype", record.dtype)
            overrides.setdefault("device", record.device)
            overrides.setdefault("context_length", record.context_length)
            if record.adapter_path:
                overrides.setdefault("adapter_path", record.adapter_path)
            if record.gguf_path:
                overrides.setdefault("gguf_path", record.gguf_path)
            if record.base_url:
                overrides.setdefault("base_url", record.base_url)

    status = registry.load(settings, overrides)
    record_action(
        session,
        "model.load",
        target_type="model",
        target_id=status.model_id,
        detail={"backend": status.backend, "quantization": status.quantization_mode},
    )
    return ModelStatus(**status.as_dict())


@router.post("/unload", response_model=ModelStatus, summary="Release the loaded model")
def unload_model(session: Session = Depends(get_session)) -> ModelStatus:
    status = registry.unload()
    record_action(session, "model.unload", target_type="model", target_id=status.model_id)
    return ModelStatus(**status.as_dict())


@router.post("/register", response_model=ModelSummary, summary="Add a model to the catalogue")
def register_model(
    payload: ModelRegisterRequest, session: Session = Depends(get_session)
) -> ModelSummary:
    record = ModelRecord(**payload.model_dump(), is_builtin=False)
    session.add(record)
    session.commit()
    session.refresh(record)
    record_action(
        session, "model.register", target_type="model", target_id=record.id,
        detail={"model_id": record.model_id, "backend": record.backend},
    )
    return ModelSummary(**record.model_dump())


@router.delete("/{record_id}", response_model=ModelSummary, summary="Remove a custom model")
def delete_model(record_id: str, session: Session = Depends(get_session)) -> ModelSummary:
    record = session.get(ModelRecord, record_id)
    if record is None:
        raise NotFoundError(f"Model {record_id} is not registered.")
    if record.is_builtin:
        from ..errors import ConflictError

        raise ConflictError("Built-in catalogue entries cannot be deleted.")
    summary = ModelSummary(**record.model_dump())
    session.delete(record)
    session.commit()
    record_action(session, "model.delete", target_type="model", target_id=record_id)
    return summary
