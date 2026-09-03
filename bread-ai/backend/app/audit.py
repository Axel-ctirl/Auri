"""Append-only audit trail for state-changing actions.

The log is local only. It exists so an operator can answer "what changed and
when" without turning on any kind of remote telemetry.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from .models import AuditLog


def record_action(
    session: Session,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    actor: str = "local",
    detail: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor=actor,
        detail_json=json.dumps(detail, default=str) if detail else None,
    )
    session.add(entry)
    if commit:
        session.commit()
        session.refresh(entry)
    return entry


def recent_actions(session: Session, limit: int = 100) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    return list(session.exec(statement).all())
