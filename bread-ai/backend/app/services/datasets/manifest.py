"""Dataset manifests: what was collected, from where, under which terms.

Every collection run writes a manifest next to its JSONL output. It is the
record you need months later when someone asks where a training example came
from, and it is what makes a redistribution decision possible at all.
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DatasetManifest:
    name: str
    source: str
    output_path: str
    record_count: int = 0
    dataset_name: str | None = None
    source_url: str | None = None
    terms_url: str | None = None
    license_summary: dict[str, int] = field(default_factory=dict)
    language_summary: dict[str, int] = field(default_factory=dict)
    subset: str | None = None
    configuration: dict[str, Any] = field(default_factory=dict)
    size_limits: dict[str, Any] = field(default_factory=dict)
    accepted_terms: bool = False
    accepted_terms_at: str | None = None
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    collector_host: str = field(default_factory=platform.node)
    warnings: list[str] = field(default_factory=list)
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path | None = None) -> Path:
        target = Path(path) if path else Path(self.output_path).with_suffix(".manifest.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return target


def standard_warnings(source: str) -> list[str]:
    shared = [
        "Review every upstream license before you redistribute this data, publish "
        "fine-tuned weights trained on it, or use it commercially.",
        "A permissive label on a dataset does not make every record inside it safe "
        "for every use. Upstream labels can be wrong or incomplete.",
    ]
    per_source = {
        "the_stack": [
            "The Stack has an opt-out process. Respect removal requests and re-check "
            "the current opt-out list before publishing anything derived from it.",
        ],
        "codesearchnet": [
            "CodeSearchNet mixes licenses across repositories. Its per-record license "
            "field is the one that matters, not the dataset-level label.",
        ],
        "fineweb_edu": [
            "FineWeb-Edu is web-crawled text. It carries the usual web-scale risks: "
            "copyrighted passages, personal data and low-quality pages.",
        ],
        "openwebtext": [
            "OpenWebText is an experimental reconstruction of web text with unclear "
            "per-document provenance. Treat it as research material.",
        ],
    }
    return shared + per_source.get(source, [])


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
