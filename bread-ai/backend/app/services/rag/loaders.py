"""Reading uploaded files safely and turning them into plain text.

Two rules run through this module:

* Uploaded source code is *data*. Bread reads it, hashes it and embeds it. It is
  never imported, evaluated or executed.
* Filenames from the browser are hostile until proven otherwise, so every path
  is rebuilt from a sanitised basename inside the uploads directory.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ...errors import BreadError, ValidationFailedError

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".java",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".lua",
    ".luau",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".sql",
    ".sh",
    ".html",
    ".css",
    ".yaml",
    ".yml",
}
BINARY_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".lua": "lua",
    ".luau": "luau",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
    ".sh": "bash",
    ".html": "html",
    ".css": "css",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".csv": "csv",
    ".txt": "text",
    ".pdf": "pdf",
}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class LoadedDocument:
    text: str
    extension: str
    language: str
    content_hash: str
    size_bytes: int


def sanitize_filename(raw_name: str, *, fallback: str = "upload.txt") -> str:
    """Reduce a browser-supplied name to a safe basename.

    Strips directory components, normalises Unicode, drops anything outside
    ``[A-Za-z0-9._-]`` and refuses names that would resolve outside the uploads
    directory.
    """

    candidate = (raw_name or "").replace("\\", "/").split("/")[-1]
    candidate = unicodedata.normalize("NFKD", candidate)
    candidate = candidate.encode("ascii", "ignore").decode("ascii")
    candidate = _UNSAFE_CHARS.sub("_", candidate).strip("._")
    if not candidate or candidate in {".", ".."}:
        candidate = fallback
    if len(candidate) > 180:
        stem, _, suffix = candidate.rpartition(".")
        candidate = (stem[:150] + "." + suffix) if suffix else candidate[:180]
    return candidate


def resolve_upload_path(uploads_dir: Path, filename: str) -> Path:
    """Build a collision-free path inside ``uploads_dir`` and verify containment."""

    uploads_dir = uploads_dir.resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    target = (uploads_dir / safe_name).resolve()

    if uploads_dir not in target.parents and target != uploads_dir:
        raise ValidationFailedError(
            "Rejected an upload path that escaped the uploads directory.",
            code="path_traversal_blocked",
        )

    counter = 1
    stem, suffix = target.stem, target.suffix
    while target.exists():
        target = (uploads_dir / f"{stem}_{counter}{suffix}").resolve()
        counter += 1
    return target


def check_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValidationFailedError(
            f"Bread does not index '{extension or 'files with no extension'}'.",
            code="unsupported_file_type",
            hint="Supported types: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        )
    return extension


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_document(path: Path) -> LoadedDocument:
    """Read a stored file into text. Never executes the file's contents."""

    extension = path.suffix.lower()
    payload = path.read_bytes()
    digest = hash_bytes(payload)

    text = _extract_pdf_text(path) if extension == ".pdf" else _decode_text(payload)

    return LoadedDocument(
        text=text,
        extension=extension,
        language=LANGUAGE_BY_EXTENSION.get(extension, "text"),
        content_hash=digest,
        size_bytes=len(payload),
    )


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: keep what decodes and drop the rest rather than failing the
    # whole upload for a few stray bytes.
    return payload.decode("utf-8", errors="replace")


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise BreadError(
            "PDF support needs the 'pypdf' package.",
            code="pdf_support_missing",
            hint="pip install pypdf",
            status_code=503,
        ) from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        if extracted.strip():
            pages.append(f"[page {page_number}]\n{extracted.strip()}")
    return "\n\n".join(pages)
