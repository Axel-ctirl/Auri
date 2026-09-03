"""Reading the local audit trail.

The log records state-changing actions so an operator can answer "what changed
and when" without any form of remote telemetry. It never leaves this machine.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..audit import recent_actions
from ..db import get_session

router = APIRouter(prefix="/audit-logs", tags=["security"])


class AuditEntry(BaseModel):
    id: str
    action: str
    target_type: str | None = None
    target_id: str | None = None
    actor: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


@router.get("", response_model=list[AuditEntry], summary="Recent state-changing actions")
def list_audit_entries(
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[AuditEntry]:
    entries: list[AuditEntry] = []
    for record in recent_actions(session, limit=limit):
        detail: dict[str, Any] = {}
        if record.detail_json:
            try:
                parsed = json.loads(record.detail_json)
                detail = parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                detail = {"raw": record.detail_json}
        entries.append(
            AuditEntry(
                id=record.id,
                action=record.action,
                target_type=record.target_type,
                target_id=record.target_id,
                actor=record.actor,
                detail=detail,
                created_at=record.created_at,
            )
        )
    return entries
