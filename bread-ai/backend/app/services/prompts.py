"""System prompt and task-preset loading.

Presets are Markdown files under ``prompts/presets/``. The first ``# heading``
becomes the title, the first paragraph after it becomes the description, an
optional ``Triggers:`` line lists the words that should select it, and the rest
of the file is appended to the system prompt.

A preset only helps if it reaches the model. The web interface has a dropdown;
a terminal has a question, so ``suggest`` picks the preset whose triggers the
question actually contains. Getting this wrong is cheap (a paragraph of
irrelevant guidance) and getting it right is worth a lot to a small model, which
does not reliably remember that reading message content needs a privileged
intent.

A preset may ship a worked example beside it, named ``<preset>.reference.<ext>``.
Bread's tests check every Python reference the same way they check a model's
answer, so the example the model is shown is one that actually works.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT
from ..errors import NotFoundError

PRESET_DIR = REPO_ROOT / "prompts" / "presets"


TRIGGER_PREFIX = "Triggers:"
REFERENCE_LANGUAGES = {
    ".py": "python",
    ".lua": "lua",
    ".luau": "lua",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sh": "bash",
    ".dockerfile": "dockerfile",
}


def _parse(path: Path) -> dict[str, Any]:
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

    triggers: list[str] = []
    for index in range(body_start, min(body_start + 3, len(lines))):
        candidate = lines[index].strip()
        if candidate.startswith(TRIGGER_PREFIX):
            triggers = [
                word.strip().lower()
                for word in candidate[len(TRIGGER_PREFIX) :].split(",")
                if word.strip()
            ]
            body_start = index + 1
            break

    return {
        "name": path.stem,
        "title": title,
        "description": description,
        "triggers": triggers,
        "body": "\n".join(lines[body_start:]).strip(),
        "reference": _reference_for(path),
    }


def _reference_for(path: Path) -> dict[str, str] | None:
    """A worked example shipped beside the preset, if there is one."""

    for candidate in sorted(path.parent.glob(f"{path.stem}.reference.*")):
        return {
            "filename": candidate.name,
            "language": REFERENCE_LANGUAGES.get(candidate.suffix, ""),
            "code": candidate.read_text(encoding="utf-8").strip(),
        }
    return None


@lru_cache(maxsize=1)
def list_presets() -> list[dict[str, Any]]:
    if not PRESET_DIR.exists():
        return []
    return [_parse(path) for path in sorted(PRESET_DIR.glob("*.md"))]


def get_preset(name: str) -> dict[str, Any]:
    safe = re.sub(r"[^a-z0-9_-]", "", name.lower())
    for preset in list_presets():
        if preset["name"] == safe:
            return preset
    raise NotFoundError(
        f"No prompt preset named '{name}'.",
        hint="GET /api/prompts/presets lists the available names.",
    )


def suggest(question: str) -> str | None:
    """The preset whose triggers this question actually contains, if any.

    A trigger is worth its word count plus a bonus for appearing early in the
    list, because the first triggers in a preset are the ones that identify it:
    "fastapi" names the FastAPI preset, while "endpoint" merely appears in it.
    Without that, the longest word won and a FastAPI question landed on the
    generic REST preset.

    Nothing is returned when nothing matched. A preset applied to the wrong
    question is worse than no preset.
    """

    text = f" {re.sub(r'[^a-z0-9+.# ]+', ' ', (question or '').lower())} "
    best: tuple[float, str] | None = None
    for preset in list_presets():
        score = 0.0
        for position, trigger in enumerate(preset["triggers"]):
            if f" {trigger} " in text:
                score += len(trigger.split()) + 1 / (1 + position)
        if score and (best is None or score > best[0]):
            best = (score, preset["name"])
    return best[1] if best else None


def compose_system_prompt(
    base: str, preset_name: str | None = None, *, include_reference: bool = True
) -> str:
    if not preset_name:
        return base
    preset = get_preset(preset_name)
    parts = [base, f"## Task preset: {preset['title']}", preset["body"]]

    reference = preset.get("reference")
    if include_reference and reference:
        parts.append(
            "### A worked example that runs\n\n"
            f"This is `{reference['filename']}`, checked against the installed libraries. "
            "Follow its shape and its precautions. Do not copy it back verbatim when the "
            "user asked for something else.\n\n"
            f"```{reference['language']}\n{reference['code']}\n```"
        )
    return "\n\n".join(parts)


def clear_preset_cache() -> None:
    list_presets.cache_clear()
