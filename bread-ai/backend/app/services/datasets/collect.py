"""Dataset collection.

Three rules govern this module:

1. Local, user-owned folders are the recommended source and need no extra flags.
2. Anything that leaves the machine needs an explicit terms acceptance from the
   operator. There is no implicit download and no website scraping.
3. Every record keeps its provenance, and every run writes a manifest.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from .code_tasks import (
    ExtractionStats,
    build_tasks,
    build_test_tasks,
    extract_units,
    is_worth_training_on,
)
from .licenses import (
    DEFAULT_ALLOWED_LICENSES,
    LICENSE_FILENAMES,
    detect_repository_license,
    is_allowed,
)
from .manifest import DatasetManifest, standard_warnings
from .records import RecordMeta, make_chat_record, make_text_record, write_jsonl
from .secrets import contains_secret

LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "java": (".java",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx"),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp", ".cc", ".hh", ".cxx"),
    "csharp": (".cs",),
    "go": (".go",),
    "rust": (".rs",),
    "kotlin": (".kt", ".kts"),
    "php": (".php",),
    "ruby": (".rb",),
    "sql": (".sql",),
    "bash": (".sh", ".bash"),
    "html": (".html", ".htm"),
    "css": (".css", ".scss"),
    "json": (".json",),
    "yaml": (".yaml", ".yml"),
    "markdown": (".md", ".markdown"),
    "lua": (".lua",),
    "luau": (".luau",),
}

SUPPORTED_LANGUAGES = tuple(LANGUAGE_EXTENSIONS)

EXTENSION_TO_LANGUAGE = {
    extension: language
    for language, extensions in LANGUAGE_EXTENSIONS.items()
    for extension in extensions
}

ENGLISH_EXTENSIONS = (".txt", ".md", ".markdown", ".rst")

SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "out",
    "target",
    ".gradle",
    ".idea",
    ".vscode",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    "third_party",
    "site-packages",
    ".tox",
    "coverage",
    ".nuxt",
    "bin",
    "obj",
}

SKIP_FILE_HINTS = (
    ".min.js",
    ".min.css",
    ".lock",
    "-lock.json",
    ".map",
    ".snap",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Cargo.lock",
)

DEFAULT_MAX_FILE_BYTES = 512 * 1024

EXTERNAL_SOURCES: dict[str, dict[str, str]] = {
    "codesearchnet": {
        "dataset_name": "code-search-net/code_search_net",
        "source_url": "https://huggingface.co/datasets/code-search-net/code_search_net",
        "terms_url": "https://huggingface.co/datasets/code-search-net/code_search_net",
    },
    "the_stack": {
        "dataset_name": "bigcode/the-stack-smol",
        "source_url": "https://huggingface.co/datasets/bigcode/the-stack-smol",
        "terms_url": "https://huggingface.co/datasets/bigcode/the-stack#terms-of-use",
    },
    "fineweb_edu": {
        "dataset_name": "HuggingFaceFW/fineweb-edu",
        "source_url": "https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu",
        "terms_url": "https://huggingface.co/datasets/HuggingFaceFW/fineweb-edu",
    },
    "openwebtext": {
        "dataset_name": "Skylion007/openwebtext",
        "source_url": "https://huggingface.co/datasets/Skylion007/openwebtext",
        "terms_url": "https://huggingface.co/datasets/Skylion007/openwebtext",
    },
}


class TermsNotAcceptedError(RuntimeError):
    """Raised when an external download is attempted without an explicit opt-in."""


@dataclass
class CollectionOptions:
    name: str
    output_path: Path
    languages: tuple[str, ...] = SUPPORTED_LANGUAGES
    max_records: int = 2000
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    allowed_licenses: tuple[str, ...] = DEFAULT_ALLOWED_LICENSES
    require_license: bool = True
    skip_secrets: bool = True
    accept_terms: bool = False
    dataset_name: str | None = None
    dataset_config: str | None = None
    split: str = "train"
    instruction_style: bool = True
    # Which instruction tasks to derive from each documented definition. See
    # code_tasks.py for what each one teaches.
    task_kinds: tuple[str, ...] = ("implement", "explain", "document", "test")


# ------------------------------------------------------------------ local code
def iter_source_files(
    roots: list[Path],
    *,
    languages: tuple[str, ...],
    max_file_bytes: int,
    extensions: tuple[str, ...] | None = None,
) -> Iterator[tuple[Path, Path, str]]:
    """Yield ``(repo_root, file_path, language)`` for every eligible file."""

    if extensions is None:
        allowed_extensions = tuple(
            extension
            for language in languages
            for extension in LANGUAGE_EXTENSIONS.get(language, ())
        )
    else:
        allowed_extensions = extensions

    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRECTORIES]
            current = Path(dirpath)
            for filename in filenames:
                if any(hint in filename for hint in SKIP_FILE_HINTS):
                    continue
                path = current / filename
                extension = path.suffix.lower()
                if extension not in allowed_extensions:
                    continue
                try:
                    if path.stat().st_size > max_file_bytes:
                        continue
                except OSError:
                    continue
                language = EXTENSION_TO_LANGUAGE.get(extension, "text")
                yield root, path, language


PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
)


def find_project_root(file_path: Path, base_root: Path) -> Path:
    """Walk up from a file to the project it belongs to.

    Pointing the collector at a folder of checkouts is the normal case, so the
    license that matters is the one next to the file's own project, not the one
    at the top of the workspace.
    """

    current = file_path.parent
    while True:
        has_license = any((current / name).exists() for name in LICENSE_FILENAMES)
        has_marker = any((current / name).exists() for name in PROJECT_MARKERS)
        if has_license or has_marker:
            return current
        if current == base_root or current.parent == current:
            return base_root
        current = current.parent


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def collect_local_code(
    roots: list[Path],
    options: CollectionOptions,
    *,
    progress: Callable[[int], None] | None = None,
) -> tuple[int, DatasetManifest]:
    """Walk local folders you own and build an instruction dataset from them."""

    license_cache: dict[Path, str] = {}
    license_counts: dict[str, int] = {}
    language_counts: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    skipped_secret = 0
    skipped_license = 0
    stats = ExtractionStats()
    units_by_repo: dict[Path, list[tuple[list[Any], RecordMeta]]] = {}

    for base_root, path, language in iter_source_files(
        roots,
        languages=options.languages,
        max_file_bytes=options.max_file_bytes,
    ):
        if len(records) >= options.max_records:
            break

        repo_root = find_project_root(path, base_root)
        if repo_root not in license_cache:
            license_cache[repo_root] = detect_repository_license(repo_root).license_id
        license_id = license_cache[repo_root]

        if options.require_license and not is_allowed(
            license_id, options.allowed_licenses
        ):
            skipped_license += 1
            continue

        text = _read_text(path)
        if not text or not text.strip():
            continue
        if options.skip_secrets and contains_secret(text):
            skipped_secret += 1
            continue

        relative = path.relative_to(repo_root).as_posix()
        meta = RecordMeta(
            source="local_code",
            license=license_id,
            language=language,
            path=relative,
            repo=repo_root.name,
        )

        if options.instruction_style:
            # Derive real tasks from the documentation the code already carries,
            # rather than asking the model to restate a file back at us.
            stats.files += 1
            units = extract_units(text, language, relative)
            stats.units_found += len(units)
            units_by_repo.setdefault(repo_root, []).append((units, meta))

            new_records: list[dict[str, Any]] = []
            for unit in units:
                built = build_tasks(unit, meta, kinds=options.task_kinds)
                if built:
                    stats.units_accepted += 1
                else:
                    accepted, reason = is_worth_training_on(unit)
                    if not accepted:
                        stats.reject(reason)
                new_records.extend(built)

            if not new_records:
                continue
            records.extend(new_records)
        else:
            records.append(make_text_record(text, meta))

        license_counts[license_id] = license_counts.get(license_id, 0) + 1
        language_counts[language] = language_counts.get(language, 0) + 1
        if progress and len(records) % 100 == 0:
            progress(len(records))

    # Tests are matched to the functions they exercise across a whole project,
    # so this pass happens after every file in the repo has been read.
    if options.instruction_style and "test" in options.task_kinds:
        for repo_units in units_by_repo.values():
            flattened = [unit for units, _meta in repo_units for unit in units]
            if not flattened:
                continue
            first_meta = repo_units[0][1]
            records.extend(build_test_tasks(flattened, first_meta))

    records = records[: options.max_records]
    stats.records = len(records)

    written = write_jsonl(options.output_path, records)
    manifest = DatasetManifest(
        name=options.name,
        source="local_code",
        output_path=str(options.output_path),
        record_count=written,
        license_summary=license_counts,
        language_summary=language_counts,
        configuration={
            "roots": [str(root) for root in roots],
            "languages": list(options.languages),
            "require_license": options.require_license,
            "allowed_licenses": list(options.allowed_licenses),
            "skipped_for_license": skipped_license,
            "skipped_for_secrets": skipped_secret,
            "task_kinds": list(options.task_kinds),
            "extraction": stats.as_dict(),
        },
        size_limits={
            "max_records": options.max_records,
            "max_file_bytes": options.max_file_bytes,
        },
        accepted_terms=True,
        notes="Collected from local folders the operator pointed at. No network access.",
        warnings=standard_warnings("local_code"),
    )
    manifest.write()
    return written, manifest


def collect_local_english(
    roots: list[Path],
    options: CollectionOptions,
) -> tuple[int, DatasetManifest]:
    """Collect plain-English text you own: notes, docs, articles you wrote."""

    records: list[dict[str, Any]] = []
    for base_root, path, _language in iter_source_files(
        roots,
        languages=(),
        max_file_bytes=options.max_file_bytes,
        extensions=ENGLISH_EXTENSIONS,
    ):
        if len(records) >= options.max_records:
            break
        repo_root = find_project_root(path, base_root)
        text = _read_text(path)
        if not text or len(text.strip()) < 200:
            continue
        if options.skip_secrets and contains_secret(text):
            continue
        records.append(
            make_text_record(
                text,
                RecordMeta(
                    source="local_english",
                    license="USER_OWNED",
                    language="english",
                    path=path.relative_to(repo_root).as_posix(),
                    repo=repo_root.name,
                ),
            )
        )

    written = write_jsonl(options.output_path, records)
    manifest = DatasetManifest(
        name=options.name,
        source="local_english",
        output_path=str(options.output_path),
        record_count=written,
        language_summary={"english": written},
        configuration={"roots": [str(root) for root in roots]},
        size_limits={"max_records": options.max_records},
        accepted_terms=True,
        notes="Plain-English files from folders the operator pointed at.",
        warnings=standard_warnings("local_english"),
    )
    manifest.write()
    return written, manifest


# --------------------------------------------------------------- external data
def collect_huggingface(
    source: str,
    options: CollectionOptions,
) -> tuple[int, DatasetManifest]:
    """Download a bounded sample from a Hugging Face dataset, after opt-in."""

    if not options.accept_terms:
        raise TermsNotAcceptedError(
            f"Collecting '{source}' downloads data from an external host. Re-run with "
            "--accept-terms (CLI) or accept_terms=true (API) once you have read the "
            "upstream terms, and keep in mind that a dataset-level label does not "
            "make every record inside it safe for your use."
        )

    descriptor = EXTERNAL_SOURCES.get(source, {})
    dataset_name = options.dataset_name or descriptor.get("dataset_name")
    if not dataset_name:
        raise ValueError(
            f"No Hugging Face dataset is configured for source '{source}'."
        )

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "The 'datasets' package is required for external collection. "
            "pip install datasets"
        ) from exc

    stream = load_dataset(
        dataset_name,
        options.dataset_config,
        split=options.split,
        streaming=True,
    )

    records: list[dict[str, Any]] = []
    license_counts: dict[str, int] = {}
    language_counts: dict[str, int] = {}
    skipped_license = 0
    skipped_secret = 0

    for row in stream:
        if len(records) >= options.max_records:
            break

        text, language, license_id, url = _normalize_external_row(row, source)
        if not text or len(text) < 80:
            continue
        if len(text) > options.max_file_bytes:
            continue
        if (
            options.require_license
            and license_id != "UNKNOWN"
            and not is_allowed(license_id, options.allowed_licenses)
        ):
            skipped_license += 1
            continue
        if options.skip_secrets and contains_secret(text):
            skipped_secret += 1
            continue

        meta = RecordMeta(
            source=source,
            source_url=url or descriptor.get("source_url"),
            license=license_id,
            language=language,
        )
        docstring = (
            row.get("func_documentation_string") if isinstance(row, dict) else None
        )
        if source == "codesearchnet" and docstring:
            record = make_chat_record(
                system="You are Bread, a local coding assistant.",
                user=f"Write a {language} function that does the following:\n\n{docstring.strip()}",
                assistant=f"```{language}\n{text}\n```",
                meta=meta,
            )
        else:
            record = make_text_record(text, meta)

        records.append(record)
        license_counts[license_id] = license_counts.get(license_id, 0) + 1
        language_counts[language] = language_counts.get(language, 0) + 1

    written = write_jsonl(options.output_path, records)
    from datetime import datetime

    manifest = DatasetManifest(
        name=options.name,
        source=source,
        output_path=str(options.output_path),
        record_count=written,
        dataset_name=dataset_name,
        source_url=descriptor.get("source_url"),
        terms_url=descriptor.get("terms_url"),
        license_summary=license_counts,
        language_summary=language_counts,
        subset=options.dataset_config,
        configuration={
            "split": options.split,
            "streaming": True,
            "require_license": options.require_license,
            "allowed_licenses": list(options.allowed_licenses),
            "skipped_for_license": skipped_license,
            "skipped_for_secrets": skipped_secret,
        },
        size_limits={
            "max_records": options.max_records,
            "max_record_bytes": options.max_file_bytes,
        },
        accepted_terms=True,
        accepted_terms_at=datetime.now(UTC).isoformat(timespec="seconds"),
        warnings=standard_warnings(source),
    )
    manifest.write()
    return written, manifest


def _normalize_external_row(row: Any, source: str) -> tuple[str, str, str, str | None]:
    """Map one upstream row onto ``(text, language, license, url)``."""

    if not isinstance(row, dict):
        return str(row), "text", "UNKNOWN", None

    text = ""
    for key in ("content", "func_code_string", "whole_func_string", "text", "code"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            text = value
            break

    language = str(
        row.get("language")
        or row.get("lang")
        or ("english" if source in {"fineweb_edu", "openwebtext"} else "text")
    ).lower()

    license_value = row.get("license") or row.get("licenses") or "UNKNOWN"
    if isinstance(license_value, list):
        license_value = license_value[0] if license_value else "UNKNOWN"
    license_id = str(license_value).strip() or "UNKNOWN"

    url = row.get("url") or row.get("repository_url") or row.get("repo_name")
    return text, language, license_id, (str(url) if url else None)
