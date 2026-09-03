"""API-facing glue around the dataset library.

Collection runs in a worker thread so a long walk over a big source tree does
not block the event loop. Each run is recorded in the ``dataset_runs`` table
together with its manifest.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..config import REPO_ROOT, Settings
from ..errors import NotFoundError, ValidationFailedError
from ..models import DatasetRun, utcnow
from .datasets import (
    DEFAULT_ALLOWED_LICENSES,
    EXTERNAL_SOURCES,
    SUPPORTED_LANGUAGES,
    CollectionOptions,
    TermsNotAcceptedError,
    build_report,
    collect_huggingface,
    collect_local_code,
    collect_local_english,
    validate_file,
)

LOCAL_SOURCES = {"local_code", "local_english"}


def resolve_dataset_path(settings: Settings, raw_path: str) -> Path:
    """Resolve a caller-supplied dataset path and keep it inside known roots.

    A path traversal here would let an API client read arbitrary files through
    the report endpoint, so containment is checked rather than assumed.
    """

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = (settings.datasets_path / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = [settings.datasets_path.resolve(), settings.data_dir.resolve()]
    if not any(
        root == candidate or root in candidate.parents for root in allowed_roots
    ):
        raise ValidationFailedError(
            "Dataset paths must live under the Bread data directory.",
            code="path_outside_data_dir",
            hint=f"Move the file under {settings.datasets_path} and try again.",
        )
    return candidate


def list_runs(session: Session, limit: int = 100) -> list[DatasetRun]:
    statement = select(DatasetRun).order_by(DatasetRun.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    return list(session.exec(statement).all())


def start_collection(
    session: Session,
    settings: Settings,
    request: Any,
) -> DatasetRun:
    """Validate the request, create the run row and kick off the worker thread."""

    source = request.source
    if (
        source not in LOCAL_SOURCES
        and source not in EXTERNAL_SOURCES
        and source != "huggingface"
    ):
        raise ValidationFailedError(f"Unknown dataset source '{source}'.")

    if source in LOCAL_SOURCES and not request.input_paths:
        raise ValidationFailedError(
            "Local collection needs at least one folder to read.",
            hint="Pass input_paths, for example ['C:/projects/my-plugin'].",
        )

    if source not in LOCAL_SOURCES and not request.accept_terms:
        descriptor = EXTERNAL_SOURCES.get(source, {})
        raise ValidationFailedError(
            f"'{source}' downloads data from an external host, so it needs an "
            "explicit terms acceptance.",
            code="terms_not_accepted",
            hint="Read the upstream terms, then resend with accept_terms=true.",
            details={"terms_url": descriptor.get("terms_url", "")},
        )

    languages = tuple(request.languages) if request.languages else SUPPORTED_LANGUAGES
    unknown = [name for name in languages if name not in SUPPORTED_LANGUAGES]
    if unknown:
        raise ValidationFailedError(
            f"Unsupported languages: {', '.join(unknown)}.",
            hint=f"Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
        )

    output_path = settings.datasets_path / f"{_slug(request.name)}.jsonl"
    descriptor = EXTERNAL_SOURCES.get(source, {})

    run = DatasetRun(
        name=request.name,
        kind="collect",
        source=source,
        output_path=str(output_path),
        accepted_terms=bool(request.accept_terms) or source in LOCAL_SOURCES,
        terms_url=descriptor.get("terms_url"),
        status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    options = CollectionOptions(
        name=request.name,
        output_path=output_path,
        languages=languages,
        max_records=request.max_records,
        max_file_bytes=request.max_file_bytes,
        allowed_licenses=tuple(request.allow_licenses or DEFAULT_ALLOWED_LICENSES),
        skip_secrets=request.scan_secrets,
        accept_terms=bool(request.accept_terms),
        dataset_name=request.hf_dataset,
        dataset_config=request.hf_config,
        split=request.hf_split,
    )
    roots = [_resolve_input_path(path) for path in request.input_paths]

    worker = threading.Thread(
        target=_run_collection,
        args=(run.id, source, roots, options),
        name=f"bread-collect-{run.id[:8]}",
        daemon=True,
    )
    worker.start()
    return run


def _resolve_input_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def _slug(name: str) -> str:
    cleaned = "".join(
        character if character.isalnum() else "_" for character in name.lower()
    )
    return cleaned.strip("_") or "dataset"


def _run_collection(
    run_id: str,
    source: str,
    roots: list[Path],
    options: CollectionOptions,
) -> None:
    from ..db import new_session

    with new_session() as session:
        run = session.get(DatasetRun, run_id)
        if run is None:
            return
        try:
            if source == "local_code":
                written, manifest = collect_local_code(roots, options)
            elif source == "local_english":
                written, manifest = collect_local_english(roots, options)
            else:
                written, manifest = collect_huggingface(source, options)

            run.record_count = written
            run.manifest_json = json.dumps(manifest.as_dict())
            run.license_summary = json.dumps(manifest.license_summary)
            run.status = "completed"
        except TermsNotAcceptedError as exc:
            run.status = "failed"
            run.error = str(exc)
        except Exception as exc:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        finally:
            run.finished_at = utcnow()
            session.add(run)
            session.commit()


def validate_dataset(
    settings: Settings, path: str, schema_name: str, max_records: int | None
):
    resolved = resolve_dataset_path(settings, path)
    if not resolved.exists():
        raise NotFoundError(f"No dataset file at {resolved}.")
    return validate_file(resolved, schema_name, max_records=max_records)


def dataset_report(settings: Settings, path: str) -> dict[str, Any]:
    resolved = resolve_dataset_path(settings, path)
    if not resolved.exists():
        raise NotFoundError(f"No dataset file at {resolved}.")
    return build_report(resolved)
