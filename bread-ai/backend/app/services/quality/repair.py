"""Generate, verify, and repair: the loop that makes generated code run.

A model that invents an API does not know it did. It will happily correct the
mistake when shown it, which makes the failure recoverable rather than fatal.
This module closes that loop: generate an answer, check every name and signature
against the libraries actually installed, hand any provable problems back to the
model, and try again.

Two limits keep it honest. Only *certain* findings trigger a repair, because
asking a model to fix a suspicion invites it to break working code. And the
attempt that survives is the one with the fewest remaining problems, not
necessarily the last, so a repair that makes things worse is discarded.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..inference.base import ChatTurn, GenerationParams, InferenceBackend, StopSignal
from .api_check import ApiReport, check_answer

MAX_ATTEMPTS = 3

REPAIR_INSTRUCTION = """Your previous answer will not run. Checking it against \
the libraries installed on this machine found these problems:

{problems}

Return the corrected code. Change only what is needed to fix these problems, \
keep everything that already worked, and do not explain what you changed unless \
it is not obvious from the code."""


@dataclass
class Attempt:
    number: int
    answer: str
    report: ApiReport

    @property
    def problem_count(self) -> int:
        return len(self.report.certain)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.number,
            "problems": self.problem_count,
            "findings": [finding.as_dict() for finding in self.report.certain],
        }


@dataclass
class RepairResult:
    answer: str
    attempts: list[Attempt] = field(default_factory=list)
    repaired: bool = False

    @property
    def final_report(self) -> ApiReport | None:
        return self.attempts[-1].report if self.attempts else None

    @property
    def problems_remaining(self) -> int:
        best = min((attempt.problem_count for attempt in self.attempts), default=0)
        return best

    def as_dict(self) -> dict[str, Any]:
        return {
            "repaired": self.repaired,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "problems_remaining": self.problems_remaining,
            "problems_at_first_attempt": (self.attempts[0].problem_count if self.attempts else 0),
        }


def describe_problems(report: ApiReport) -> str:
    """Render findings as instructions a model can act on."""

    lines = []
    if report.syntax_error:
        lines.append(f"- The code does not parse: {report.syntax_error}")
    for finding in report.certain:
        lines.append(f"- Line {finding.line}: {finding.message}")
    return "\n".join(lines)


def generate_verified(
    backend: InferenceBackend,
    turns: list[ChatTurn],
    params: GenerationParams,
    *,
    stop_signal: StopSignal | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    allow_import: bool = True,
    on_attempt: Callable[[Attempt], None] | None = None,
) -> RepairResult:
    """Generate an answer, then repair it until its references resolve."""

    conversation = list(turns)
    result = RepairResult(answer="")

    for number in range(1, max(max_attempts, 1) + 1):
        if stop_signal is not None and stop_signal.stopped:
            break

        answer = backend.generate(conversation, params, stop_signal)
        report = check_answer(answer, allow_import=allow_import)
        attempt = Attempt(number=number, answer=answer, report=report)
        result.attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)

        # No code to check is not a code problem, so there is nothing to repair.
        if report.syntax_error == "no code block in the answer":
            break
        if not report.certain and not report.syntax_error:
            break
        if number == max_attempts:
            break

        conversation = [
            *conversation,
            ChatTurn(role="assistant", content=answer),
            ChatTurn(
                role="user",
                content=REPAIR_INSTRUCTION.format(problems=describe_problems(report)),
            ),
        ]

    if not result.attempts:
        return result

    # Keep the cleanest attempt rather than the last one: a repair that
    # introduces more problems than it fixes should not win by being newest.
    best = min(result.attempts, key=lambda attempt: (attempt.problem_count, attempt.number))
    result.answer = best.answer
    result.repaired = (
        len(result.attempts) > 1 and best.problem_count < result.attempts[0].problem_count
    )
    return result


def memory_notes(result: RepairResult) -> list[str]:
    """Turn repaired mistakes into sentences worth remembering.

    A mistake the model made once it will make again. Storing the correction is
    how the second time is avoided.
    """

    if not result.attempts:
        return []

    notes: list[str] = []
    fixed_kinds = {"attribute", "keyword"}
    for finding in result.attempts[0].report.certain:
        if finding.kind not in fixed_kinds:
            continue
        notes.append(finding.message.replace("`", ""))
    return notes[:5]
