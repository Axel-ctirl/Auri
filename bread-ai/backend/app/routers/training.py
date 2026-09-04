"""Fine-tuning run control."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..audit import record_action
from ..config import REPO_ROOT, Settings, get_settings
from ..db import get_session
from ..schemas import (
    TrainingLogsResponse,
    TrainingRunOut,
    TrainingStartRequest,
    TrainingStopRequest,
)
from ..services import training_service

router = APIRouter(prefix="/training", tags=["training"])


@router.get("/runs", response_model=list[TrainingRunOut], summary="List training runs")
def list_runs(session: Session = Depends(get_session)) -> list[TrainingRunOut]:
    return [TrainingRunOut(**run.model_dump()) for run in training_service.list_runs(session)]


@router.get("/configs", summary="List the training configs that ship with Bread")
def list_configs() -> list[dict]:
    # Fine-tuning configs and from-scratch pretraining configs, in one list.
    paths = sorted((REPO_ROOT / "configs" / "training").glob("*.yaml"))
    paths += sorted((REPO_ROOT / "configs" / "pretrain").glob("*.yaml"))
    entries: list[dict] = []
    for path in paths:
        try:
            config = training_service.load_config(path)
        except Exception:
            config = {}
        is_pretrain = path.parent.name == "pretrain"
        entries.append(
            {
                "path": str(Path(path).relative_to(REPO_ROOT).as_posix()),
                "name": path.stem,
                "base_model_id": config.get("base_model_id", ""),
                "method": "pretrain" if is_pretrain else config.get("method", "qlora"),
                "description": config.get("description", "")
                or (
                    f"Pretrain {config.get('name', path.stem)} from random "
                    "initialisation. No inherited weights."
                ),
                "min_vram_gb": config.get("min_vram_gb"),
            }
        )
    return entries


@router.post("/start", response_model=TrainingRunOut, summary="Start a fine-tuning run")
def start_training(
    payload: TrainingStartRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TrainingRunOut:
    """Launch training in a separate process.

    Send ``dry_run: true`` first: it checks the config, the dataset and the GPU
    and reports every problem it finds without starting anything.
    """

    run = training_service.start_run(session, settings, payload)
    record_action(
        session,
        "training.start" if not payload.dry_run else "training.dry_run",
        target_type="training_run",
        target_id=run.id,
        detail={"config": payload.config_path, "method": payload.method},
    )
    return TrainingRunOut(**run.model_dump())


@router.post("/stop", response_model=TrainingRunOut, summary="Stop a running job")
def stop_training(
    payload: TrainingStopRequest, session: Session = Depends(get_session)
) -> TrainingRunOut:
    run = training_service.stop_run(session, payload.run_id)
    record_action(session, "training.stop", target_type="training_run", target_id=run.id)
    return TrainingRunOut(**run.model_dump())


@router.get("/{run_id}", response_model=TrainingRunOut, summary="Fetch one run")
def get_run(run_id: str, session: Session = Depends(get_session)) -> TrainingRunOut:
    return TrainingRunOut(**training_service.get_run(session, run_id).model_dump())


@router.get("/{run_id}/logs", response_model=TrainingLogsResponse, summary="Tail the run log")
def get_logs(
    run_id: str,
    tail: int = Query(default=400, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> TrainingLogsResponse:
    run = training_service.get_run(session, run_id)
    lines, truncated = training_service.read_logs(run, tail=tail)
    return TrainingLogsResponse(run_id=run_id, lines=lines, truncated=truncated)
