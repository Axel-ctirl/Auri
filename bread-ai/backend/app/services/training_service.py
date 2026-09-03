"""Launching and supervising local fine-tuning runs.

Training happens in a separate process. That keeps a CUDA out-of-memory crash or
a hung dataloader from taking the web server down with it, and it means you can
close the browser without killing the run.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session, select

from ..config import REPO_ROOT, Settings
from ..errors import ConflictError, NotFoundError, ValidationFailure
from ..models import TrainingCheckpoint, TrainingRun, utcnow

SCRIPTS_DIR = REPO_ROOT / "scripts"
CONFIG_ROOT = REPO_ROOT / "configs"

METHOD_SCRIPTS = {
    "qlora": "train_qlora.py",
    "lora": "train_qlora.py",
    "tiny_scratch": "train_tiny_scratch.py",
}

# Emitted by the training scripts as: BREAD_PROGRESS {"step": 10, "loss": 1.23}
_PROGRESS_RE = re.compile(r"BREAD_PROGRESS\s+(\{.*\})")

_processes: dict[str, subprocess.Popen[str]] = {}
_processes_lock = threading.Lock()


def list_runs(session: Session, limit: int = 100) -> list[TrainingRun]:
    statement = select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    return list(session.exec(statement).all())


def get_run(session: Session, run_id: str) -> TrainingRun:
    run = session.get(TrainingRun, run_id)
    if run is None:
        raise NotFoundError(f"Training run {run_id} does not exist.")
    return run


def resolve_config_path(raw_path: str) -> Path:
    """Only allow configs from inside ``configs/``. This path becomes argv."""

    candidate = Path(raw_path).expanduser()
    resolved = (candidate if candidate.is_absolute() else (REPO_ROOT / candidate)).resolve()
    config_root = CONFIG_ROOT.resolve()
    if config_root != resolved and config_root not in resolved.parents:
        raise ValidationFailure(
            "Training configs must live under configs/.",
            code="config_outside_repo",
            hint="Copy your YAML into configs/training/ and pass that path.",
        )
    if not resolved.exists():
        raise NotFoundError(f"No training config at {resolved}.")
    return resolved


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValidationFailure(f"{path} must contain a YAML mapping.")
    return loaded


def preflight(config: dict[str, Any], dataset_path: Path | None) -> list[str]:
    """Cheap checks that catch the mistakes people actually make."""

    problems: list[str] = []

    if dataset_path is not None and not dataset_path.exists():
        problems.append(f"Dataset file not found: {dataset_path}")

    required = ("base_model_id", "output_dir")
    for key in required:
        if not config.get(key):
            problems.append(f"Config is missing '{key}'.")

    try:
        import torch

        if not torch.cuda.is_available():
            problems.append(
                "No CUDA device is visible. QLoRA on CPU is not practical; expect "
                "days per epoch rather than hours."
            )
        else:
            total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            if total_gb < 10 and config.get("load_in_4bit", True):
                problems.append(
                    f"This GPU reports {total_gb:.0f} GB of VRAM. Use "
                    "configs/training/lora_small_fallback.yaml instead of a 7B QLoRA config."
                )
    except ImportError:
        problems.append("PyTorch is not installed, so no training can start.")

    for package in ("transformers", "peft", "trl", "datasets"):
        try:
            __import__(package)
        except ImportError:
            problems.append(f"'{package}' is not installed. See requirements-train.txt.")

    return problems


def start_run(session: Session, settings: Settings, request: Any) -> TrainingRun:
    config_path = resolve_config_path(request.config_path)
    config = load_config(config_path)

    dataset_raw = request.dataset_path or config.get("dataset_path", "")
    dataset_path: Path | None = None
    if dataset_raw:
        candidate = Path(dataset_raw).expanduser()
        dataset_path = candidate if candidate.is_absolute() else (REPO_ROOT / candidate).resolve()

    problems = preflight(config, dataset_path)
    base_model_id = request.base_model_id or config.get("base_model_id", settings.model_id)
    output_dir = (settings.runs_dir / _slug(request.name)).resolve()

    run = TrainingRun(
        name=request.name,
        method=request.method,
        base_model_id=base_model_id,
        dataset_path=str(dataset_path or ""),
        config_path=str(config_path),
        config_json=json.dumps(config),
        output_dir=str(output_dir),
        status="pending",
    )

    if request.dry_run:
        run.status = "completed" if not problems else "failed"
        run.error = "\n".join(problems) if problems else None
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    if problems:
        run.status = "failed"
        run.error = "\n".join(problems)
        run.finished_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)
        raise ValidationFailure(
            "The run cannot start yet.",
            code="training_preflight_failed",
            details={"problems": problems, "run_id": run.id},
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "train.log"
    run.log_path = str(log_path)
    session.add(run)
    session.commit()
    session.refresh(run)

    script = SCRIPTS_DIR / METHOD_SCRIPTS.get(request.method, "train_qlora.py")
    command = [
        sys.executable,
        str(script),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
        "--run-id",
        run.id,
    ]
    if dataset_path:
        command += ["--dataset", str(dataset_path)]
    if request.base_model_id:
        command += ["--base-model-id", request.base_model_id]

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(  # noqa: S603 - argv is built from validated paths
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
        bufsize=1,
    )

    with _processes_lock:
        _processes[run.id] = process

    run.pid = process.pid
    run.status = "running"
    run.started_at = utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)

    threading.Thread(
        target=_pump_logs,
        args=(run.id, process, log_path),
        name=f"bread-train-{run.id[:8]}",
        daemon=True,
    ).start()

    return run


def _pump_logs(run_id: str, process: subprocess.Popen[str], log_path: Path) -> None:
    from ..db import new_session

    last_step = 0
    last_loss: float | None = None

    with log_path.open("a", encoding="utf-8") as log_file:
        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            match = _PROGRESS_RE.search(line)
            if not match:
                continue
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            last_step = int(payload.get("step", last_step))
            if payload.get("loss") is not None:
                last_loss = float(payload["loss"])
            with new_session() as session:
                run = session.get(TrainingRun, run_id)
                if run is None:
                    continue
                run.current_step = last_step
                run.train_loss = last_loss
                if payload.get("total_steps"):
                    run.total_steps = int(payload["total_steps"])
                if payload.get("eval_loss") is not None:
                    run.eval_loss = float(payload["eval_loss"])
                if payload.get("checkpoint"):
                    session.add(
                        TrainingCheckpoint(
                            run_id=run_id,
                            step=last_step,
                            path=str(payload["checkpoint"]),
                            train_loss=last_loss,
                        )
                    )
                session.add(run)
                session.commit()

    return_code = process.wait()
    with _processes_lock:
        _processes.pop(run_id, None)

    with new_session() as session:
        run = session.get(TrainingRun, run_id)
        if run is None:
            return
        if run.status == "stopped":
            pass
        elif return_code == 0:
            run.status = "completed"
        else:
            run.status = "failed"
            run.error = run.error or (
                f"The training process exited with code {return_code}. "
                f"See {log_path} for the traceback."
            )
        run.finished_at = utcnow()
        session.add(run)
        session.commit()


def stop_run(session: Session, run_id: str) -> TrainingRun:
    run = get_run(session, run_id)
    if run.status != "running":
        raise ConflictError(f"Run '{run.name}' is not running (status: {run.status}).")

    with _processes_lock:
        process = _processes.get(run_id)

    if process is not None:
        _terminate(process)
    elif run.pid:
        # The server restarted while the run kept going; fall back to the pid.
        try:
            os.kill(run.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    run.status = "stopped"
    run.finished_at = utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _terminate(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def read_logs(run: TrainingRun, tail: int = 400) -> tuple[list[str], bool]:
    if not run.log_path:
        return [], False
    path = Path(run.log_path)
    if not path.exists():
        return [], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= tail:
        return lines, False
    return lines[-tail:], True


def _slug(name: str) -> str:
    cleaned = "".join(character if character.isalnum() else "-" for character in name.lower())
    return cleaned.strip("-") or "run"
