"""System prompt and task-preset loading.

Presets are Markdown files under ``prompts/presets/``. The first ``# heading``
becomes the title, the first paragraph after it becomes the description, and the
whole file (minus that header block) is appended to the system prompt.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ..config import REPO_ROOT
from ..errors import NotFoundError

PRESET_DIR = REPO_ROOT / "prompts" / "presets"


def _parse(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()
    title = path.stem.replace("_", " ").title()
    description = ""
    body_start = 0

    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        body_start = 1
        for index in range(1, len(lines)):
            candidate = lines[index].strip()
            if candidate:
                description = candidate
                body_start = index + 1
                break

    return {
        "name": path.stem,
        "title": title,
        "description": description,
        "body": "\n".join(lines[body_start:]).strip(),
    }


@lru_cache(maxsize=1)
def list_presets() -> list[dict[str, str]]:
    if not PRESET_DIR.exists():
        return []
    return [_parse(path) for path in sorted(PRESET_DIR.glob("*.md"))]


def get_preset(name: str) -> dict[str, str]:
    safe = re.sub(r"[^a-z0-9_-]", "", name.lower())
    for preset in list_presets():
        if preset["name"] == safe:
            return preset
    raise NotFoundError(
        f"No prompt preset named '{name}'.",
        hint="GET /api/prompts/presets lists the available names.",
    )


def compose_system_prompt(base: str, preset_name: str | None = None) -> str:
    if not preset_name:
        return base
    preset = get_preset(preset_name)
    return f"{base}\n\n## Task preset: {preset['title']}\n\n{preset['body']}"


def clear_preset_cache() -> None:
    list_presets.cache_clear()
