"""API-key issuance/verification and a small in-process rate limiter.

Bread binds to ``127.0.0.1`` by default, where an API key is optional. The
moment the operator binds to a LAN address the key becomes mandatory: see
``ensure_lan_guard`` which refuses to start an unauthenticated LAN server.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlmodel import Session, col, select

from .config import Settings, get_settings
from .db import get_session
from .errors import RateLimitedError, UnauthorizedError
from .models import ApiKey, utcnow

KEY_PREFIX = "bread_sk_"


@dataclass(frozen=True)
class IssuedKey:
    record: ApiKey
    plaintext: str


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key(session: Session, label: str, scopes: str = "read,write") -> IssuedKey:
    """Create a key. The plaintext is returned once and never stored."""

    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    record = ApiKey(
        label=label or "local",
        key_prefix=plaintext[: len(KEY_PREFIX) + 6],
        key_hash=hash_key(plaintext),
        scopes=scopes,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return IssuedKey(record=record, plaintext=plaintext)


def _extract_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_api_key(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApiKey | None:
    """Dependency enforcing API-key auth when the deployment requires it."""

    enforced = settings.require_api_key or settings.binds_to_lan
    presented = _extract_key(request)

    if not enforced:
        # Still honour a key when one is supplied, so `last_used_at` stays useful.
        if presented:
            record = _lookup(session, presented)
            if record is not None:
                _touch(session, record)
                return record
        return None

    if not presented:
        raise UnauthorizedError(
            "This Bread server requires an API key.",
            hint="Send it as the 'X-API-Key' header or as 'Authorization: Bearer <key>'. "
            "Create one with POST /api/api-keys from localhost, or run "
            "'python -m app.cli create-key'.",
        )

    record = _lookup(session, presented)
    if record is None:
        raise UnauthorizedError("The supplied API key is unknown or has been revoked.")
    _touch(session, record)
    return record


def _lookup(session: Session, plaintext: str) -> ApiKey | None:
    digest = hash_key(plaintext)
    statement = select(ApiKey).where(ApiKey.key_hash == digest, col(ApiKey.revoked).is_(False))
    return session.exec(statement).first()


def _touch(session: Session, record: ApiKey) -> None:
    record.last_used_at = utcnow()
    session.add(record)
    session.commit()


class RateLimiter:
    """Fixed-window-per-caller limiter kept in memory.

    Good enough for a single local process. If Bread ever runs behind more than
    one worker this needs to move into SQLite or Redis.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, caller: str) -> None:
        if self.max_requests <= 0:
            return
        now = time.monotonic()
        bucket = self._hits[caller]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            raise RateLimitedError(
                "Too many requests from this client.",
                hint=f"The limit is {self.max_requests} requests per "
                f"{self.window_seconds}s. Raise BREAD_RATE_LIMIT_REQUESTS if this is "
                "your own automation.",
            )
        bucket.append(now)

    def reset(self) -> None:
        self._hits.clear()


def caller_identity(request: Request) -> str:
    key = _extract_key(request)
    if key:
        return "key:" + hash_key(key)[:16]
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def ensure_lan_guard(settings: Settings) -> list[str]:
    """Return warnings that must be shown before a LAN bind is accepted."""

    warnings: list[str] = []
    if not settings.binds_to_lan:
        return warnings
    warnings.append(
        f"Bread is bound to {settings.host}, which is reachable from your network. "
        "Anyone who can reach this port can talk to your local model and read the "
        "documents you indexed."
    )
    if not settings.require_api_key:
        warnings.append(
            "BREAD_REQUIRE_API_KEY is off. LAN binding forces key checks on anyway, "
            "so create a key before other machines can use this server."
        )
    if not settings.allow_lan_binding:
        warnings.append("Set BREAD_ALLOW_LAN_BINDING=true to confirm you meant to expose Bread.")
    return warnings
