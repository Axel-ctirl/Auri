"""Dataset record shapes and JSONL input/output.

Bread stores every dataset as JSON Lines. Three shapes are recognised:

``sft_chat``
    ``{"messages": [{"role": ..., "content": ...}, ...], "meta": {...}}``
``sft_instruction``
    ``{"instruction": ..., "input": ..., "output": ..., "meta": {...}}``
``raw_text``
    ``{"text": ..., "meta": {...}}``

``meta`` carries provenance and is never dropped: source name, upstream URL,
license id, language, original path and a content hash.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_NAMES = ("sft_chat", "sft_instruction", "raw_text")
VALID_ROLES = {"system", "user", "assistant"}


@dataclass
class RecordMeta:
    source: str = "local"
    source_url: str | None = None
    license: str = "UNKNOWN"
    language: str = "text"
    path: str | None = None
    repo: str | None = None
    collected_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    content_sha256: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def make_chat_record(
    *,
    system: str | None,
    user: str,
    assistant: str,
    meta: RecordMeta,
) -> dict[str, Any]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    messages.append({"role": "assistant", "content": assistant})
    meta.content_sha256 = content_hash(user + "\n" + assistant)
    return {"messages": messages, "meta": meta.as_dict()}


def make_text_record(text: str, meta: RecordMeta) -> dict[str, Any]:
    meta.content_sha256 = content_hash(text)
    return {"text": text, "meta": meta.as_dict()}


def record_text(record: dict[str, Any]) -> str:
    """Flatten any supported record shape into one string for hashing/statistics."""

    if "messages" in record:
        return "\n".join(
            str(message.get("content", "")) for message in record.get("messages", [])
        )
    if "text" in record:
        return str(record.get("text", ""))
    return "\n".join(
        str(record.get(key, "")) for key in ("instruction", "input", "output")
    )


def detect_schema(record: dict[str, Any]) -> str | None:
    if isinstance(record.get("messages"), list):
        return "sft_chat"
    if "instruction" in record and "output" in record:
        return "sft_instruction"
    if isinstance(record.get("text"), str):
        return "raw_text"
    return None


def validate_record(record: dict[str, Any], schema_name: str) -> list[str]:
    """Return a list of human-readable problems. Empty means the record is fine."""

    problems: list[str] = []

    if schema_name == "sft_chat":
        messages = record.get("messages")
        if not isinstance(messages, list) or not messages:
            return ["'messages' must be a non-empty list"]
        roles = []
        for position, message in enumerate(messages):
            if not isinstance(message, dict):
                problems.append(f"messages[{position}] is not an object")
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in VALID_ROLES:
                problems.append(
                    f"messages[{position}].role '{role}' is not a valid role"
                )
            if not isinstance(content, str) or not content.strip():
                problems.append(f"messages[{position}].content is empty")
            roles.append(role)
        if "user" not in roles:
            problems.append("no user message")
        if "assistant" not in roles:
            problems.append("no assistant message")

    elif schema_name == "sft_instruction":
        for key in ("instruction", "output"):
            value = record.get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"'{key}' is missing or empty")

    elif schema_name == "raw_text":
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append("'text' is missing or empty")

    else:
        problems.append(f"unknown schema '{schema_name}'")

    meta = record.get("meta")
    if meta is not None and not isinstance(meta, dict):
        problems.append("'meta' must be an object when present")

    return problems


def read_jsonl(
    path: Path, limit: int | None = None
) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    """Yield ``(line_number, record, error)`` for each line."""

    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if limit is not None and line_number > limit:
                return
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                yield line_number, json.loads(stripped), None
            except json.JSONDecodeError as exc:
                yield line_number, None, f"invalid JSON: {exc.msg}"


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
    return written


def count_lines(path: Path) -> int:
    total = 0
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total
