"""Tasks that drive a real library's handlers, and the harness that runs them.

A generic task measures whether a function computes the right answer. These
measure whether a program built on a framework behaves, which is where a small
model actually fails: the wiring comes out right and the logic does not.
"""

from __future__ import annotations

import pytest
import yaml

from app.config import REPO_ROOT
from app.services.quality.coding_eval import (
    evaluate_answers,
    missing_requirements,
    run_snippet,
)

TASK_FILE = REPO_ROOT / "prompts" / "evals" / "framework_tasks.yaml"


def load() -> list[dict]:
    return yaml.safe_load(TASK_FILE.read_text(encoding="utf-8"))["tasks"]


def block(code: str) -> str:
    return f"```python\n{code}\n```"


WARNING_LOG = '''
"""Warnings, kept per member per server."""

from __future__ import annotations

import os
from collections import defaultdict

import disnake
from disnake.ext import commands

bot = commands.InteractionBot(intents=disnake.Intents.default())

warnings_by_member: defaultdict[tuple[int, int], list[str]] = defaultdict(list)


@bot.slash_command(name="warn", description="Record a warning against a member.")
async def warn(inter, member, reason: str) -> None:
    warnings_by_member[(member.guild.id, member.id)].append(reason)
    await inter.response.send_message(f"Warning recorded for {member.name}.", ephemeral=True)


@bot.slash_command(name="warning_count", description="How many warnings a member has here.")
async def warning_count(inter, member) -> None:
    count = len(warnings_by_member[(member.guild.id, member.id)])
    await inter.response.send_message(f"{count} warning(s) for {member.name}.", ephemeral=True)


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN before starting the bot.")
    bot.run(token)


if __name__ == "__main__":
    main()
'''

# The mistake the 1.5B model actually made: warnings keyed by the server rather
# than by the member, so every member in a server shares one count.
WARNING_LOG_KEYED_BY_SERVER = WARNING_LOG.replace(
    "member.guild.id, member.id", "member.guild.id, member.guild.id"
)


def test_the_tasks_parse_and_declare_what_they_need():
    tasks = load()
    assert tasks
    for task in tasks:
        assert task["id"] and task["prompt"].strip() and task["test"].strip()
        assert task.get("requires"), f"{task['id']} does not say what it needs"


def test_a_task_whose_library_is_absent_is_skipped_not_failed():
    """Scoring a task that never ran, either way, would make the number a lie."""

    tasks = [
        {
            "id": "needs_nothing_real",
            "requires": ["a_library_that_is_not_installed"],
            "prompt": "x",
            "test": "assert True",
        }
    ]
    card = evaluate_answers(tasks, {}, allow_execution=True)
    assert card.results[0].skipped is True
    assert card.total == 0
    assert len(card.skipped) == 1


def test_present_libraries_are_not_reported_missing():
    assert missing_requirements(["json", "collections"]) == []
    assert missing_requirements(["definitely_not_installed"]) == ["definitely_not_installed"]


def test_a_main_guard_does_not_fire_when_the_answer_is_tested():
    """A whole program run as a script would start itself and never be tested."""

    code = 'started = False\n\n\ndef main():\n    raise SystemExit("started")\n\n\nif __name__ == "__main__":\n    main()\n'
    passed, reason, detail = run_snippet(code, "assert started is False", allow_execution=True)
    assert passed, f"{reason}: {detail}"


def test_a_future_import_still_comes_first():
    code = "from __future__ import annotations\n\n\ndef total(values: list[int]) -> int:\n    return sum(values)\n"
    passed, reason, detail = run_snippet(code, "assert total([1, 2]) == 3", allow_execution=True)
    assert passed, f"{reason}: {detail}"


def test_a_docstring_still_comes_first():
    code = '"""A module."""\n\nvalue = 3\n'
    passed, reason, detail = run_snippet(code, "assert value == 3", allow_execution=True)
    assert passed, f"{reason}: {detail}"


def _task(task_id: str) -> dict:
    return next(task for task in load() if task["id"] == task_id)


@pytest.mark.slow
def test_the_warning_task_passes_a_correct_bot():
    pytest.importorskip("disnake")
    card = evaluate_answers(
        [_task("disnake_warning_log")],
        {"disnake_warning_log": block(WARNING_LOG)},
        allow_execution=True,
        timeout=60,
    )
    assert card.results[0].passed, card.results[0].detail


@pytest.mark.slow
def test_the_warning_task_catches_a_count_shared_across_members():
    """The task exists to catch this: the bug a real model produced."""

    pytest.importorskip("disnake")
    card = evaluate_answers(
        [_task("disnake_warning_log")],
        {"disnake_warning_log": block(WARNING_LOG_KEYED_BY_SERVER)},
        allow_execution=True,
        timeout=60,
    )
    result = card.results[0]
    assert not result.passed
    assert "alice" in result.detail
