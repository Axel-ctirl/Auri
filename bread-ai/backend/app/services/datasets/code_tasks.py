"""Turning real source files into genuine instruction data.

The naive way to build a coding dataset is to show the model a file and ask it
to repeat the file back. That trains copying, and a model trained on it answers
every question by reproducing its input. It is worse than no fine-tune at all.

What actually teaches is the pairing that already exists in good code: a
docstring is a human's English description of what a function does, sitting
right next to the function that does it. That single pairing yields three real
tasks, and a repository's tests yield a fourth:

``implement``   description -> code
``explain``     code -> description
``document``    undocumented code -> description
``test``        code -> a test that exercises it

Every example is written by a person. Nothing here is synthesised prose, which
is why the English stays good: the model learns from the docstrings your
project already has, filtered for the ones worth learning from.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from ..quality.english import clean_docstring, looks_like_prose, score_prose
from .records import RecordMeta, make_chat_record

TASK_KINDS = ("implement", "explain", "document", "test")

MIN_BODY_LINES = 3
MAX_BODY_LINES = 80
MIN_DOCSTRING_WORDS = 8

SYSTEM_PROMPT = (
    "You are Bread, a local coding assistant. Answer in professional English, "
    "write correct and readable code, and say plainly when you are unsure."
)


@dataclass
class CodeUnit:
    """One documented function, method or class pulled out of a source file."""

    name: str
    kind: str  # function | method | class
    language: str
    signature: str
    source: str
    docstring: str
    start_line: int
    end_line: int
    path: str = ""
    is_test: bool = False
    source_without_docstring: str = ""

    @property
    def body_lines(self) -> int:
        return self.source.count("\n") + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "language": self.language,
            "signature": self.signature,
            "lines": self.body_lines,
            "path": self.path,
        }


# --------------------------------------------------------------------- python
def extract_python_units(source: str, path: str = "") -> list[CodeUnit]:
    """Pull documented definitions out of Python source using the real parser."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    units: list[CodeUnit] = []

    def signature_of(node: ast.AST) -> str:
        if isinstance(node, ast.ClassDef):
            return f"class {node.name}"
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        arguments = ast.unparse(node.args) if hasattr(ast, "unparse") else ""
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"{prefix} {node.name}({arguments}){returns}"

    def visit(node: ast.AST, inside_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                docstring = ast.get_docstring(child) or ""
                start = child.lineno - 1
                end = getattr(child, "end_lineno", child.lineno)
                body = "\n".join(lines[start:end])

                units.append(
                    CodeUnit(
                        name=child.name,
                        kind="class"
                        if isinstance(child, ast.ClassDef)
                        else ("method" if inside_class else "function"),
                        language="python",
                        signature=signature_of(child),
                        source=body,
                        docstring=docstring,
                        start_line=child.lineno,
                        end_line=end,
                        path=path,
                        is_test=child.name.startswith("test_"),
                        source_without_docstring=_strip_python_docstring(body, docstring),
                    )
                )
                visit(child, isinstance(child, ast.ClassDef))

    visit(tree, False)
    return units


def _strip_python_docstring(body: str, docstring: str) -> str:
    """Remove the docstring literal so the code can be shown undocumented."""

    if not docstring:
        return body
    pattern = re.compile(
        r'(\n\s*)(?:"""|\'\'\')(?:.|\n)*?(?:"""|\'\'\')\s*\n', re.MULTILINE
    )
    stripped = pattern.sub("\n", body, count=1)
    return stripped if stripped.strip() else body


# -------------------------------------------------------------------- generic
# Doc comment styles by language family. Each pattern captures the comment and
# the signature line that follows it.
_DOC_COMMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "block": re.compile(
        r"/\*\*(?P<doc>(?:[^*]|\*(?!/))*)\*/\s*\n(?P<signature>[^\n{;]{4,200})",
        re.MULTILINE,
    ),
    "slashes": re.compile(
        r"(?P<doc>(?:^[ \t]*///[^\n]*\n)+)(?P<signature>[^\n{;]{4,200})",
        re.MULTILINE,
    ),
    "hash": re.compile(
        r"(?P<doc>(?:^[ \t]*--[^\[\n][^\n]*\n)+)(?P<signature>[^\n\n]{4,200})",
        re.MULTILINE,
    ),
}

_LANGUAGE_COMMENT_STYLE = {
    "java": "block", "javascript": "block", "typescript": "block",
    "csharp": "slashes", "rust": "slashes", "go": "slashes",
    "cpp": "block", "c": "block", "php": "block", "kotlin": "block",
    "lua": "hash", "luau": "hash",
}

_NAME_IN_SIGNATURE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def extract_generic_units(source: str, language: str, path: str = "") -> list[CodeUnit]:
    """Pull doc-commented definitions out of a non-Python source file.

    This is regex work rather than parsing, so it is conservative: it only
    accepts a doc comment immediately followed by something that looks like a
    signature, and it stops the body at the matching brace depth.
    """

    style = _LANGUAGE_COMMENT_STYLE.get(language)
    if not style:
        return []

    pattern = _DOC_COMMENT_PATTERNS[style]
    units: list[CodeUnit] = []

    for match in pattern.finditer(source):
        raw_doc = match.group("doc")
        signature = match.group("signature").strip()
        if not signature or signature.startswith(("//", "*", "#", "--")):
            continue

        docstring = _clean_comment_markers(raw_doc, style)
        name_match = _NAME_IN_SIGNATURE.search(signature)
        if not name_match:
            continue

        body = _capture_body(source, match.end("signature"), signature, style)
        if not body:
            continue

        start_line = source[: match.start()].count("\n") + 1
        units.append(
            CodeUnit(
                name=name_match.group(1),
                kind="function",
                language=language,
                signature=signature,
                source=body,
                docstring=docstring,
                start_line=start_line,
                end_line=start_line + body.count("\n"),
                path=path,
                is_test="test" in name_match.group(1).lower(),
                source_without_docstring=body,
            )
        )

    return units


def _clean_comment_markers(raw: str, style: str) -> str:
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        for marker in ("///", "*", "--", "//"):
            if stripped.startswith(marker):
                stripped = stripped[len(marker) :].strip()
                break
        lines.append(stripped)
    return "\n".join(lines).strip()


def _capture_body(source: str, signature_end: int, signature: str, style: str) -> str:
    """Take the signature plus its braced body, or its indented block for Lua."""

    signature_start = source.rfind("\n", 0, signature_end - len(signature)) + 1
    remainder = source[signature_end:]

    if style == "hash":  # Lua and Luau use end-terminated blocks
        end_match = re.search(r"\nend\b", remainder)
        if not end_match:
            return ""
        return source[signature_start : signature_end + end_match.end()]

    opening = remainder.find("{")
    if opening == -1 or opening > 200:
        return ""

    depth = 0
    for offset, character in enumerate(remainder[opening:], start=opening):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[signature_start : signature_end + offset + 1]
    return ""


# ------------------------------------------------------------------- filtering
def is_worth_training_on(unit: CodeUnit) -> tuple[bool, str]:
    """Decide whether a unit makes a good training example, and say why not."""

    if not unit.docstring.strip():
        return False, "no docstring"

    prose = clean_docstring(unit.docstring)
    if not looks_like_prose(prose):
        return False, "docstring is reference markup, not prose"
    if len(prose.split()) < MIN_DOCSTRING_WORDS:
        return False, f"docstring is {len(prose.split())} words"

    quality = score_prose(prose)
    if not quality.is_good:
        return False, f"docstring quality {quality.score:.2f}: {'; '.join(quality.problems)}"

    if unit.body_lines < MIN_BODY_LINES:
        return False, f"only {unit.body_lines} lines"
    if unit.body_lines > MAX_BODY_LINES:
        return False, f"{unit.body_lines} lines is too long to learn from"

    return True, ""


# ----------------------------------------------------------------------- tasks
def build_tasks(
    unit: CodeUnit,
    meta: RecordMeta,
    kinds: tuple[str, ...] = ("implement", "explain", "document"),
) -> list[dict[str, Any]]:
    """Turn one documented unit into instruction records."""

    accepted, _reason = is_worth_training_on(unit)
    if not accepted:
        return []

    description = clean_docstring(unit.docstring)
    language = unit.language
    records: list[dict[str, Any]] = []

    def record(user: str, assistant: str, task: str) -> dict[str, Any]:
        task_meta = RecordMeta(
            source=f"{meta.source}/{task}",
            source_url=meta.source_url,
            license=meta.license,
            language=meta.language,
            path=meta.path,
            repo=meta.repo,
            notes=f"{task} task built from {unit.kind} {unit.name}",
        )
        return make_chat_record(
            system=SYSTEM_PROMPT, user=user, assistant=assistant, meta=task_meta
        )

    if "implement" in kinds and unit.kind != "class":
        records.append(
            record(
                f"Write a {language} {unit.kind} with this signature:\n\n"
                f"```{language}\n{unit.signature}\n```\n\n"
                f"It should do the following.\n\n{description}",
                f"```{language}\n{unit.source}\n```",
                "implement",
            )
        )

    if "explain" in kinds:
        records.append(
            record(
                f"Explain what this {language} {unit.kind} does.\n\n"
                f"```{language}\n{unit.source}\n```",
                description,
                "explain",
            )
        )

    if "document" in kinds and unit.source_without_docstring != unit.source:
        records.append(
            record(
                f"Write documentation for this {language} {unit.kind}.\n\n"
                f"```{language}\n{unit.source_without_docstring}\n```",
                description,
                "document",
            )
        )

    return records


def build_test_tasks(
    units: list[CodeUnit], meta: RecordMeta
) -> list[dict[str, Any]]:
    """Pair each function with a test that exercises it, where one exists.

    A test is matched to a function when the test's body mentions the function's
    name. That is a loose criterion and it produces genuine pairs, because a test
    that calls a function is a real example of how to test it.
    """

    tests = [unit for unit in units if unit.is_test and unit.body_lines >= MIN_BODY_LINES]
    targets = {
        unit.name: unit
        for unit in units
        if not unit.is_test and unit.kind != "class" and len(unit.name) > 3
    }
    if not tests or not targets:
        return []

    records: list[dict[str, Any]] = []
    used: set[str] = set()

    for test in tests:
        for name, target in targets.items():
            if name in used or not re.search(rf"\b{re.escape(name)}\s*\(", test.source):
                continue
            used.add(name)
            records.append(
                make_chat_record(
                    system=SYSTEM_PROMPT,
                    user=f"Write a unit test for this {target.language} function.\n\n"
                    f"```{target.language}\n{target.source}\n```",
                    assistant=f"```{target.language}\n{test.source}\n```",
                    meta=RecordMeta(
                        source=f"{meta.source}/test",
                        license=meta.license,
                        language=meta.language,
                        path=meta.path,
                        repo=meta.repo,
                        notes=f"test task pairing {test.name} with {target.name}",
                    ),
                )
            )
            break

    return records


def extract_units(source: str, language: str, path: str = "") -> list[CodeUnit]:
    """Dispatch to the right extractor for a language."""

    if language == "python":
        return extract_python_units(source, path)
    return extract_generic_units(source, language, path)


@dataclass
class ExtractionStats:
    files: int = 0
    units_found: int = 0
    units_accepted: int = 0
    records: int = 0
    rejections: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        key = reason.split(":")[0]
        self.rejections[key] = self.rejections.get(key, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "units_found": self.units_found,
            "units_accepted": self.units_accepted,
            "records": self.records,
            "rejections": dict(sorted(self.rejections.items(), key=lambda kv: -kv[1])),
        }
