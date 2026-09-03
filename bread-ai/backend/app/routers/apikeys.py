"""API-key issuance and revocation.

Keys matter when Bread is exposed beyond localhost. The plaintext is returned
once at creation; only its SHA-256 hash is stored.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..audit import record_action
from ..db import get_session
from ..errors import NotFoundError
from ..models import ApiKey
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut, DeleteResponse
from ..security import generate_api_key

router = APIRouter(prefix="/api-keys", tags=["security"])


@router.get("", response_model=list[ApiKeyOut], summary="List API keys")
def list_keys(session: Session = Depends(get_session)) -> list[ApiKeyOut]:
    keys = session.exec(select(ApiKey).order_by(col(ApiKey.created_at).desc())).all()
    return [ApiKeyOut(**key.model_dump(exclude={"key_hash"})) for key in keys]


@router.post("", response_model=ApiKeyCreated, summary="Create an API key")
def create_key(
    payload: ApiKeyCreate, session: Session = Depends(get_session)
) -> ApiKeyCreated:
    issued = generate_api_key(session, payload.label, payload.scopes)
    record_action(
        session, "api_key.create", target_type="api_key", target_id=issued.record.id,
        detail={"label": issued.record.label},
    )
    return ApiKeyCreated(
        **issued.record.model_dump(exclude={"key_hash"}), key=issued.plaintext
    )


@router.delete("/{key_id}", response_model=DeleteResponse, summary="Revoke an API key")
def revoke_key(key_id: str, session: Session = Depends(get_session)) -> DeleteResponse:
    record = session.get(ApiKey, key_id)
    if record is None:
        raise NotFoundError(f"API key {key_id} does not exist.")
    record.revoked = True
    session.add(record)
    session.commit()
    record_action(session, "api_key.revoke", target_type="api_key", target_id=key_id)
    return DeleteResponse(deleted=True, id=key_id)
