"""Measuring coding ability by running the code, not by reading it.

Every other signal about a model's coding skill is a proxy. Perplexity says it
finds your data unsurprising. A human skim says it looks plausible. Running the
code against a test the model never saw says whether it works.

Safety
------
This module executes text produced by a language model. That is exactly the
thing Bread refuses to do anywhere else, so it is fenced in:

* It never runs unless the caller passes ``allow_execution=True``, which the CLI
  gates behind an explicit flag.
* Each snippet runs in a separate short-lived subprocess with a timeout, in a
  temporary working directory that is deleted afterwards.
* Nothing here is reachable from the HTTP API.

A subprocess is isolation, not a sandbox. A determined payload can still touch
the filesystem and the network with your user's permissions. Run evaluations on
models and task files you trust, and read the tasks before you run them.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FENCE = re.compile(r"^(?P<indent>\s*)```(?P<language>[A-Za-z0-9_+-]*)\s*$")
PYTHON_LANGUAGES = {"", "python", "py", "python3"}
DEFAULT_TIMEOUT_SECONDS = 15


def extract_code(answer: str) -> str:
    """Pull the Python out of a model's answer.

    Models wrap code in fences, sometimes after a paragraph of prose and
    sometimes across several blocks. Every Python block is taken and joined,
    which handles the common case where a class and its helper arrive
    separately.

    Fences are matched line by line rather than by one regex over the whole
    answer. A regex cannot tell an opening fence from a closing one, so on an
    answer containing a shell block it pairs that block's closing fence with the
    next opening fence and returns the prose between them as code. The result
    was a real answer being reported as unparseable instead of checked.
    """

    found = _fenced_blocks(answer or "")

    # An untagged fence is Python only when the answer never tags one. A model
    # that labels its Python uses bare fences for other things: a .env file,
    # a directory listing, terminal output.
    tagged = any(language in PYTHON_LANGUAGES - {""} for language, _body in found)
    accepted = PYTHON_LANGUAGES - {""} if tagged else PYTHON_LANGUAGES

    blocks = [body for language, body in found if language in accepted and body]
    if blocks:
        return "\n\n".join(blocks).strip()

    # No fence at all: assume the whole answer is code if it parses like it.
    stripped = (answer or "").strip()
    if stripped.startswith(("def ", "class ", "import ", "from ")):
        return stripped
    return ""


def _fenced_blocks(answer: str) -> list[tuple[str, str]]:
    """Every fenced block in the answer, as (language, dedented body)."""

    blocks: list[tuple[str, str]] = []
    buffer: list[str] = []
    language = ""
    indent = 0
    in_block = False

    for line in answer.splitlines():
        match = FENCE.match(line)
        if match is None:
            if in_block:
                buffer.append(line)
            continue
        if not in_block:
            in_block = True
            language = match.group("language").lower()
            indent = len(match.group("indent"))
            buffer = []
            continue
        blocks.append((language, _dedent_block(buffer, indent)))
        in_block = False
        buffer = []

    if in_block:
        # An unclosed fence at the end of a truncated answer.
        blocks.append((language, _dedent_block(buffer, indent)))
    return blocks


def _dedent_block(lines: list[str], fence_indent: int) -> str:
    """Strip the indent a fence inherits from the list item it sits inside.

    Models put code blocks inside numbered steps, which indents every line. Left
    alone, joining two such blocks produces an IndentationError and the whole
    answer is reported as unparseable rather than checked.
    """

    body = list(lines)
    indents = [len(line) - len(line.lstrip()) for line in body if line.strip()]
    if not indents:
        return ""
    common = min([*indents, fence_indent]) if fence_indent else min(indents)
    return "\n".join(line[common:] if line.strip() else "" for line in body).strip()


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    reason: str = ""
    detail: str = ""
    difficulty: str = "medium"
    had_code: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "reason": self.reason,
            "detail": self.detail[:400],
            "difficulty": self.difficulty,
            "had_code": self.had_code,
        }


@dataclass
class Scorecard:
    results: list[TaskResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def by_difficulty(self) -> dict[str, dict[str, int]]:
        grouped: dict[str, dict[str, int]] = {}
        for result in self.results:
            bucket = grouped.setdefault(result.difficulty, {"passed": 0, "total": 0})
            bucket["total"] += 1
            bucket["passed"] += int(result.passed)
        return grouped

    def failures(self) -> list[TaskResult]:
        return [result for result in self.results if not result.passed]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "by_difficulty": self.by_difficulty(),
            "results": [result.as_dict() for result in self.results],
        }


def run_snippet(
    code: str,
    test: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    allow_execution: bool = False,
) -> tuple[bool, str, str]:
    """Run ``code`` followed by ``test`` and report whether the test passed."""

    if not allow_execution:
        raise PermissionError(
            "Refusing to execute model-generated code without allow_execution=True."
        )
    if not code.strip():
        return False, "no_code", "The answer contained no code block."

    program = (
        "# Generated by a language model and executed by Bread's evaluator.\n"
        f"{code}\n\n"
        "# ---- hidden test ----\n"
        f"{test}\n"
        'print("BREAD_EVAL_PASS")\n'
    )

    with tempfile.TemporaryDirectory(prefix="bread-eval-") as workspace:
        script = Path(workspace) / "candidate.py"
        script.write_text(program, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(script)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout", f"Did not finish within {timeout:.0f}s."

    if "BREAD_EVAL_PASS" in completed.stdout:
        return True, "", ""

    error = (completed.stderr or completed.stdout or "").strip()
    last_line = error.splitlines()[-1] if error else "no output"
    reason = "assertion" if "AssertionError" in error else "exception"
    if "SyntaxError" in error:
        reason = "syntax"
    return False, reason, last_line


def evaluate_answers(
    tasks: list[dict[str, Any]],
    answers: dict[str, str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    allow_execution: bool = False,
) -> Scorecard:
    """Score a set of model answers against their hidden tests."""

    scorecard = Scorecard()
    for task in tasks:
        task_id = str(task["id"])
        answer = answers.get(task_id, "")
        code = extract_code(answer)

        if not code:
            scorecard.results.append(
                TaskResult(
                    task_id=task_id,
                    passed=False,
                    reason="no_code",
                    detail="The answer contained no code block.",
                    difficulty=str(task.get("difficulty", "medium")),
                    had_code=False,
                )
            )
            continue

        passed, reason, detail = run_snippet(
            code, str(task["test"]), timeout=timeout, allow_execution=allow_execution
        )
        scorecard.results.append(
            TaskResult(
                task_id=task_id,
                passed=passed,
                reason=reason,
                detail=detail,
                difficulty=str(task.get("difficulty", "medium")),
            )
        )

    return scorecard
