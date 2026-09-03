"""Shared setup for Bread's command-line scripts.

The scripts reuse the same dataset and training code the API uses, so they
import from ``backend/app``. This module puts that on ``sys.path`` and exposes a
couple of small helpers the scripts all want.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def default_datasets_dir() -> Path:
    directory = REPO_ROOT / "data" / "datasets"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_output(raw: str | None, default_name: str) -> Path:
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (REPO_ROOT / path)
    return default_datasets_dir() / default_name


def print_header(title: str) -> None:
    print(f"\n{title}")
    print("=" * len(title))


def print_table(rows: dict[str, object]) -> None:
    if not rows:
        return
    width = max(len(str(key)) for key in rows)
    for key, value in rows.items():
        print(f"  {str(key).ljust(width)}  {value}")
