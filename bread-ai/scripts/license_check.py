#!/usr/bin/env python
"""Report the license Bread detects for each project under a path.

    python scripts/license_check.py --path "C:/dev" --path ~/projects

Run this before a collection run. "No records collected" almost always means the
projects have no LICENSE file Bread recognises.

Detection is heuristic and is not legal advice. It reads LICENSE files, SPDX
headers and package metadata. Read the actual license before you rely on it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import print_header

from app.services.datasets.collect import PROJECT_MARKERS, SKIP_DIRECTORIES
from app.services.datasets.licenses import (
    DEFAULT_ALLOWED_LICENSES,
    LICENSE_FILENAMES,
    detect_repository_license,
    is_allowed,
)


def find_projects(root: Path, max_depth: int = 3) -> list[Path]:
    """Directories that look like a project: a license file or a build manifest."""

    projects: list[Path] = []
    root = root.expanduser().resolve()

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        markers = LICENSE_FILENAMES + PROJECT_MARKERS
        if any((directory / name).exists() for name in markers):
            projects.append(directory)
            return
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name not in SKIP_DIRECTORIES:
                walk(child, depth + 1)

    if root.is_dir():
        walk(root, 0)
    return projects


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument(
        "--allow-license",
        action="append",
        default=[],
        metavar="LICENSE_ID",
        help="Treat this license as allowed for the purpose of this report.",
    )
    args = parser.parse_args(argv)

    allowed = tuple(DEFAULT_ALLOWED_LICENSES) + tuple(args.allow_license)
    allowed_count = 0
    blocked: list[tuple[Path, str]] = []

    for raw_path in args.paths:
        root = Path(raw_path).expanduser()
        print_header(str(root))
        projects = find_projects(root, args.max_depth)
        if not projects:
            print("  no projects found under this path")
            continue

        for project in projects:
            finding = detect_repository_license(project)
            permitted = is_allowed(finding.license_id, allowed)
            marker = "collect" if permitted else "skip  "
            print(f"  [{marker}] {finding.license_id:<14} {project}")
            print(f"            evidence: {finding.evidence}")
            if permitted:
                allowed_count += 1
            else:
                blocked.append((project, finding.license_id))

    print_header("Summary")
    print(f"  projects that would be collected: {allowed_count}")
    print(f"  projects that would be skipped:   {len(blocked)}")

    unknown = [project for project, license_id in blocked if license_id == "UNKNOWN"]
    if unknown:
        print(
            f"\n  {len(unknown)} project(s) have no license Bread could identify. "
            "Add a LICENSE file if the code is yours, or leave them out."
        )
    copyleft = [
        f"{project.name} ({license_id})"
        for project, license_id in blocked
        if license_id != "UNKNOWN"
    ]
    if copyleft:
        print(
            "\n  Recognised but excluded by default: " + ", ".join(copyleft) + "\n"
            "  Include one deliberately with --allow-license <ID>, and understand "
            "what that license asks of you before publishing weights or data."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
