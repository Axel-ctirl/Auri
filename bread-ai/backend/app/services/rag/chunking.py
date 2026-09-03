"""Line-aware chunking for prose and source code.

Chunks are cut on line boundaries so a citation can name real line numbers, and
so a code chunk rarely stops in the middle of a statement.
"""

from __future__ import annotations

from dataclasses import dataclass

CODE_EXTENSIONS = {
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
    ".json",
}

# Lines that usually start a new logical unit. Splitting just before one of
# these keeps a function's signature attached to its body.
BOUNDARY_PREFIXES = (
    "def ",
    "class ",
    "async def ",
    "func ",
    "fn ",
    "public ",
    "private ",
    "protected ",
    "export ",
    "function ",
    "local function ",
    "impl ",
    "type ",
    "interface ",
    "struct ",
    "enum ",
    "package ",
    "module ",
    "#",
    "##",
    "###",
)


@dataclass
class Chunk:
    index: int
    content: str
    start_line: int
    end_line: int
    token_estimate: int


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: about four characters per token for English and code."""

    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    *,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    extension: str = "",
) -> list[Chunk]:
    """Split ``text`` into overlapping chunks of roughly ``chunk_size`` characters."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        chunk_overlap = min(max(chunk_overlap, 0), max(chunk_size // 4, 1))

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []

    lines = normalized.split("\n")
    prefer_boundaries = extension.lower() in CODE_EXTENSIONS

    chunks: list[Chunk] = []
    start_index = 0
    chunk_number = 0

    while start_index < len(lines):
        end_index = start_index
        size = 0
        while end_index < len(lines) and size < chunk_size:
            size += len(lines[end_index]) + 1
            end_index += 1

        if prefer_boundaries and end_index < len(lines):
            end_index = _pull_back_to_boundary(lines, start_index, end_index)

        body = "\n".join(lines[start_index:end_index]).strip("\n")
        if body.strip():
            chunks.append(
                Chunk(
                    index=chunk_number,
                    content=body,
                    start_line=start_index + 1,
                    end_line=end_index,
                    token_estimate=estimate_tokens(body),
                )
            )
            chunk_number += 1

        if end_index >= len(lines):
            break

        start_index = max(
            start_index + 1, end_index - _overlap_lines(lines, end_index, chunk_overlap)
        )

    return chunks


def _overlap_lines(lines: list[str], end_index: int, chunk_overlap: int) -> int:
    """How many trailing lines to repeat in the next chunk."""

    if chunk_overlap <= 0:
        return 0
    budget = chunk_overlap
    count = 0
    cursor = end_index - 1
    while cursor >= 0 and budget > 0:
        budget -= len(lines[cursor]) + 1
        count += 1
        cursor -= 1
    return count


def _pull_back_to_boundary(lines: list[str], start_index: int, end_index: int) -> int:
    """Move the cut point back to the last structural line, if one is close by."""

    window = max(start_index + 1, end_index - 12)
    for candidate in range(end_index - 1, window - 1, -1):
        stripped = lines[candidate].lstrip()
        if not stripped:
            continue
        if stripped.startswith(BOUNDARY_PREFIXES):
            return candidate
    return end_index
