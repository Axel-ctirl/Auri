"""Dataset collection, validation and reporting endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..audit import record_action
from ..config import Settings, get_settings
from ..db import get_session
from ..schemas import (
    DatasetCollectRequest,
    DatasetReportResponse,
    DatasetRunOut,
    DatasetValidateRequest,
    DatasetValidateResponse,
    DatasetValidationIssue,
)
from ..services import datasets_service
from ..services.datasets import EXTERNAL_SOURCES, SUPPORTED_LANGUAGES

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetRunOut], summary="List dataset runs")
def list_dataset_runs(session: Session = Depends(get_session)) -> list[DatasetRunOut]:
    return [
        DatasetRunOut(**run.model_dump()) for run in datasets_service.list_runs(session)
    ]


@router.get("/sources", summary="Which sources exist and what they require")
def list_sources() -> dict:
    """Describes every collection source, including its terms URL.

    Local folders are the recommended default. External sources are listed with
    the terms you must read and accept before Bread will download anything.
    """

    return {
        "local": [
            {
                "id": "local_code",
                "title": "Local code folders",
                "requires_terms": False,
                "notes": "Recommended. Walks folders you own, checks each repository's "
                "license file, and skips files that look like they hold secrets.",
            },
            {
                "id": "local_english",
                "title": "Local English text",
                "requires_terms": False,
                "notes": "Notes, documentation and articles you wrote.",
            },
        ],
        "external": [
            {
                "id": source_id,
                "title": source_id.replace("_", " ").title(),
                "requires_terms": True,
                "dataset_name": descriptor["dataset_name"],
                "source_url": descriptor["source_url"],
                "terms_url": descriptor["terms_url"],
            }
            for source_id, descriptor in EXTERNAL_SOURCES.items()
        ],
        "languages": list(SUPPORTED_LANGUAGES),
        "notice": "Bread never scrapes websites and never downloads an external "
        "dataset without an explicit terms acceptance. A permissive dataset label "
        "does not make every record inside it safe for your use.",
    }


@router.post("/collect", response_model=DatasetRunOut, summary="Start a collection run")
def collect_dataset(
    payload: DatasetCollectRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DatasetRunOut:
    run = datasets_service.start_collection(session, settings, payload)
    record_action(
        session,
        "dataset.collect",
        target_type="dataset_run",
        target_id=run.id,
        detail={"source": payload.source, "accepted_terms": payload.accept_terms},
    )
    return DatasetRunOut(**run.model_dump())


@router.post(
    "/validate",
    response_model=DatasetValidateResponse,
    summary="Validate a JSONL dataset",
)
def validate_dataset(
    payload: DatasetValidateRequest, settings: Settings = Depends(get_settings)
) -> DatasetValidateResponse:
    report = datasets_service.validate_dataset(
        settings, payload.path, payload.schema_name, payload.max_records
    )
    data = report.as_dict()
    return DatasetValidateResponse(
        path=data["path"],
        total_records=data["total_records"],
        valid_records=data["valid_records"],
        invalid_records=data["invalid_records"],
        duplicate_records=data["duplicate_records"],
        secret_hits=data["secret_hits"],
        issues=[DatasetValidationIssue(**issue) for issue in data["issues"]],
    )


@router.get(
    "/report", response_model=DatasetReportResponse, summary="Summarise a dataset"
)
def dataset_report(
    path: str = Query(
        ..., description="Path to a .jsonl file under the data directory"
    ),
    settings: Settings = Depends(get_settings),
) -> DatasetReportResponse:
    return DatasetReportResponse(**datasets_service.dataset_report(settings, path))
