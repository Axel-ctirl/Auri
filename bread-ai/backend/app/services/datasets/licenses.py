"""License detection for collected source files.

This is a heuristic, not legal advice. It recognises the common permissive
license texts by their distinctive phrases and by SPDX identifiers found in
file headers or package metadata. Anything it cannot place is ``UNKNOWN`` and is
excluded by default.

Redistributing collected data, publishing fine-tuned weights or using either
commercially raises obligations that vary by license. Read the licenses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ALLOWED_LICENSES = (
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "CC0-1.0",
)

LICENSE_FILENAMES = (
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "LICENCE",
    "LICENCE.txt",
    "LICENCE.md",
    "COPYING",
    "COPYING.txt",
    "UNLICENSE",
    "UNLICENSE.txt",
)

# Ordered: the first matching signature wins, so more specific texts come first.
_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Apache-2.0", ("apache license", "version 2.0")),
    ("MIT", ("permission is hereby granted, free of charge",)),
    ("BSD-3-Clause", ("neither the name of", "redistributions of source code")),
    (
        "BSD-2-Clause",
        ("redistributions of source code", "redistributions in binary form"),
    ),
    ("ISC", ("permission to use, copy, modify, and/or distribute this software",)),
    (
        "Unlicense",
        ("this is free and unencumbered software released into the public domain",),
    ),
    ("CC0-1.0", ("creative commons legal code", "cc0 1.0 universal")),
    ("MPL-2.0", ("mozilla public license version 2.0",)),
    ("GPL-3.0", ("gnu general public license", "version 3")),
    ("GPL-2.0", ("gnu general public license", "version 2")),
    ("LGPL-3.0", ("gnu lesser general public license", "version 3")),
    ("AGPL-3.0", ("gnu affero general public license",)),
)

_SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.\-+]+)")

COPYLEFT_LICENSES = {"GPL-2.0", "GPL-3.0", "LGPL-3.0", "AGPL-3.0", "MPL-2.0"}


@dataclass
class LicenseFinding:
    license_id: str
    evidence: str
    path: str | None = None

    @property
    def is_known(self) -> bool:
        return self.license_id != "UNKNOWN"


def detect_from_text(text: str, *, path: str | None = None) -> LicenseFinding:
    spdx = _SPDX_RE.search(text)
    if spdx:
        return LicenseFinding(_normalize(spdx.group(1)), "SPDX identifier", path)

    lowered = text.lower()
    for license_id, needles in _SIGNATURES:
        if all(needle in lowered for needle in needles):
            return LicenseFinding(license_id, "license text signature", path)

    return LicenseFinding("UNKNOWN", "no recognised license text", path)


def detect_repository_license(root: Path) -> LicenseFinding:
    """Look for a license file at the root of a checkout."""

    root = Path(root)
    for name in LICENSE_FILENAMES:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            finding = detect_from_text(text, path=str(candidate))
            if finding.is_known:
                return finding

    package_json = root / "package.json"
    if package_json.exists():
        import json

        try:
            data = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
            declared = data.get("license")
            if isinstance(declared, str) and declared.strip():
                return LicenseFinding(
                    _normalize(declared), "package.json", str(package_json)
                )
        except (OSError, ValueError):
            pass

    for metadata_name in ("pyproject.toml", "Cargo.toml"):
        metadata = root / metadata_name
        if not metadata.exists():
            continue
        try:
            text = metadata.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(
            r'license\s*=\s*[\{"\']?\s*(?:text\s*=\s*")?([A-Za-z0-9.\-+ ]+)', text
        )
        if match:
            return LicenseFinding(
                _normalize(match.group(1)), metadata_name, str(metadata)
            )

    return LicenseFinding(
        "UNKNOWN", "no license file found at the repository root", str(root)
    )


def _normalize(raw: str) -> str:
    cleaned = raw.strip().strip('"').strip("'")
    aliases = {
        "apache 2.0": "Apache-2.0",
        "apache-2": "Apache-2.0",
        "apache2": "Apache-2.0",
        "apache-2.0": "Apache-2.0",
        "mit": "MIT",
        "mit license": "MIT",
        "bsd": "BSD-3-Clause",
        "bsd-3": "BSD-3-Clause",
        "bsd-2": "BSD-2-Clause",
        "isc": "ISC",
        "unlicense": "Unlicense",
        "cc0": "CC0-1.0",
        "cc0-1.0": "CC0-1.0",
        "public domain": "CC0-1.0",
    }
    return aliases.get(cleaned.lower(), cleaned)


def is_allowed(
    license_id: str, allowed: tuple[str, ...] | list[str] | None = None
) -> bool:
    allowlist = {item.lower() for item in (allowed or DEFAULT_ALLOWED_LICENSES)}
    return license_id.lower() in allowlist


def redistribution_warning(license_counts: dict[str, int]) -> list[str]:
    warnings: list[str] = []
    if license_counts.get("UNKNOWN"):
        warnings.append(
            f"{license_counts['UNKNOWN']} records have no detected license. Do not "
            "redistribute them and do not assume they are safe to train on."
        )
    copyleft = {
        name: count
        for name, count in license_counts.items()
        if name in COPYLEFT_LICENSES
    }
    if copyleft:
        listed = ", ".join(
            f"{name} ({count})" for name, count in sorted(copyleft.items())
        )
        warnings.append(
            f"Copyleft-licensed records are present: {listed}. Releasing weights or "
            "data derived from them may carry obligations. Check with the licenses "
            "before you publish."
        )
    if license_counts.get("Apache-2.0"):
        warnings.append(
            "Apache-2.0 records require preserving attribution and NOTICE files if "
            "you redistribute the data."
        )
    return warnings
