"""Scoring the written English in a model's answers against a rubric.

Prose cannot be scored the way code can, because there is no test to run. What
can be measured honestly is form: does the answer lead with the answer, is it
free of filler, are the sentences readable, does it include code when code was
asked for, and does it decline to invent facts it cannot know.

A high score means well-formed writing. It says nothing about whether the
content is true. The runner prints the answers so a person can judge that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .english import score_prose

CODE_FENCE = re.compile(r"```", re.MULTILINE)


@dataclass
class ProseTaskResult:
    task_id: str
    passed: bool
    score: float
    checks: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    answer_preview: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": self.checks,
            "notes": self.notes,
            "answer_preview": self.answer_preview,
        }


@dataclass
class ProseScorecard:
    results: list[ProseTaskResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(result.score for result in self.results) / len(self.results)

    def failures(self) -> list[ProseTaskResult]:
        return [result for result in self.results if not result.passed]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.passed / self.total, 4) if self.total else 0.0,
            "mean_score": round(self.mean_score, 3),
            "results": [result.as_dict() for result in self.results],
        }


def prose_only(answer: str) -> str:
    """Strip fenced code so the prose is scored on its own."""

    return re.sub(r"```.*?```", " ", answer or "", flags=re.DOTALL).strip()


def evaluate_prose_task(task: dict[str, Any], answer: str) -> ProseTaskResult:
    """Apply one task's rubric to one answer."""

    task_id = str(task["id"])
    text = answer or ""
    narrative = prose_only(text)
    checks: dict[str, bool] = {}
    notes: list[str] = []

    if not text.strip():
        return ProseTaskResult(
            task_id=task_id,
            passed=False,
            score=0.0,
            checks={"answered": False},
            notes=["empty answer"],
        )
    checks["answered"] = True

    if task.get("require_code"):
        has_code = len(CODE_FENCE.findall(text)) >= 2
        checks["includes_code"] = has_code
        if not has_code:
            notes.append("asked for code and gave none")

    for pattern in task.get("forbid", []) or []:
        hit = re.search(pattern, narrative or text)
        key = f"avoids:{pattern[:28]}"
        checks[key] = hit is None
        if hit:
            notes.append(f"said {hit.group(0)[:60]!r}, which the rubric forbids")

    required_any = task.get("require_any") or []
    if required_any:
        matched = any(re.search(pattern, text) for pattern in required_any)
        checks["says_the_necessary_thing"] = matched
        if not matched:
            notes.append("did not say the thing this task exists to test")

    quality_score = 1.0
    if task.get("require_prose"):
        quality = score_prose(narrative)
        minimum = float(task.get("min_prose_score", 0.6))
        quality_score = quality.score
        checks["prose_quality"] = quality.score >= minimum
        if quality.score < minimum:
            notes.append(f"prose scored {quality.score:.2f} below {minimum:.2f}")
        notes.extend(quality.problems)

    if task.get("max_words"):
        words = len(narrative.split())
        within = words <= int(task["max_words"])
        checks["length"] = within
        if not within:
            notes.append(f"{words} words against a limit of {task['max_words']}")

    passed = all(checks.values())
    # The reported score blends rubric compliance with measured prose quality,
    # so a well-written answer that misses the point still scores poorly.
    compliance = sum(checks.values()) / max(len(checks), 1)
    score = compliance * 0.7 + quality_score * 0.3

    return ProseTaskResult(
        task_id=task_id,
        passed=passed,
        score=score,
        checks=checks,
        notes=notes,
        answer_preview=" ".join(text.split())[:200],
    )


def evaluate_prose(tasks: list[dict[str, Any]], answers: dict[str, str]) -> ProseScorecard:
    scorecard = ProseScorecard()
    for task in tasks:
        scorecard.results.append(evaluate_prose_task(task, answers.get(str(task["id"]), "")))
    return scorecard
