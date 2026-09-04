"""The command line: the banner, memory management, and checking a file."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from app.cli import app

runner = CliRunner()


@pytest.fixture()
def cli(bread_env):
    """The CLI, pointed at the throwaway database the other tests use."""

    from app.db import init_db

    init_db(bread_env)
    return runner


def test_bare_invocation_shows_the_banner_and_what_to_do(cli):
    result = cli.invoke(app, [])
    assert result.exit_code == 0
    # The wordmark is ASCII art, so check for the tagline and the commands.
    assert "local coding assistant" in result.stdout
    assert "bread memory add" in result.stdout


def test_status_is_one_line(cli):
    result = cli.invoke(app, ["status"])
    assert result.exit_code == 0
    assert result.stdout.strip().count("\n") == 0
    assert "backend mock" in result.stdout


def test_remembering_and_listing(cli):
    added = cli.invoke(
        app, ["memory", "add", "Prefers disnake over discord.py", "--kind", "preference"]
    )
    assert added.exit_code == 0
    listed = cli.invoke(app, ["memory", "list"])
    assert "disnake" in listed.stdout
    assert "preference" in listed.stdout


def test_an_unknown_kind_is_rejected_not_stored(cli):
    result = cli.invoke(app, ["memory", "add", "something", "--kind", "opinion"])
    assert result.exit_code == 2
    assert "kind must be one of" in result.stdout


def test_project_memory_is_listed_only_where_it_applies(cli, tmp_path):
    here = tmp_path / "here"
    elsewhere = tmp_path / "elsewhere"
    here.mkdir()
    elsewhere.mkdir()

    cli.invoke(app, ["memory", "add", "Pinned to disnake 2.12.1", "--project", str(here)])
    assert "disnake" in cli.invoke(app, ["memory", "list", "--project", str(here)]).stdout
    assert "disnake" not in cli.invoke(app, ["memory", "list", "--project", str(elsewhere)]).stdout


def test_forgetting_by_id_prefix(cli):
    cli.invoke(app, ["memory", "add", "A note to drop"])
    listed = cli.invoke(app, ["memory", "list"]).stdout
    entry_id = listed.splitlines()[1].split()[0]
    forgotten = cli.invoke(app, ["memory", "forget", entry_id])
    assert forgotten.exit_code == 0
    assert "nothing remembered yet" in cli.invoke(app, ["memory", "list"]).stdout


def test_forgetting_an_unknown_id_fails_loudly(cli):
    result = cli.invoke(app, ["memory", "forget", "deadbeef"])
    assert result.exit_code == 1
    assert "no entry" in result.stdout


def test_check_reports_an_invented_api(cli, tmp_path):
    source = tmp_path / "broken.py"
    source.write_text(
        "import itertools\n\n\ndef go(items):\n    return itertools.batched_chunks(items, 3)\n",
        encoding="utf-8",
    )
    result = cli.invoke(app, ["check", str(source)])
    assert result.exit_code == 1
    assert "batched_chunks" in result.stdout


def test_check_passes_clean_code(cli, tmp_path):
    source = tmp_path / "fine.py"
    source.write_text("def add(left, right):\n    return left + right\n", encoding="utf-8")
    result = cli.invoke(app, ["check", str(source)])
    assert result.exit_code == 0


def test_check_needs_a_file_that_exists(cli, tmp_path):
    result = cli.invoke(app, ["check", str(tmp_path / "nope.py")])
    assert result.exit_code != 0


def test_ask_answers_and_records_the_question(cli):
    result = cli.invoke(app, ["ask", "What is a linear equation?", "--raw", "--no-verify"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_doctor_names_what_is_missing(cli):
    result = cli.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "python" in result.stdout


def test_bracketed_text_is_not_read_as_markup(cli):
    """A memory entry is text, not console styling."""

    cli.invoke(app, ["memory", "add", "Prefer List[int] over bare list"])
    listed = cli.invoke(app, ["memory", "list"])
    assert listed.exit_code == 0
    assert "List[int]" in listed.stdout


def test_asking_recalls_memory(cli):
    cli.invoke(app, ["memory", "add", "Roblox scripts use Luau strict mode"])
    result = cli.invoke(app, ["ask", "Write me a Roblox script", "--no-verify"])
    assert "recalled 1 memory entry" in result.stdout


def test_memory_can_be_left_out_of_a_question(cli):
    cli.invoke(app, ["memory", "add", "Roblox scripts use Luau strict mode"])
    result = cli.invoke(app, ["ask", "Write me a Roblox script", "--no-verify", "--no-memory"])
    assert "recalled" not in result.stdout


def test_system_prompt_is_printable(cli):
    result = cli.invoke(app, ["system-prompt"])
    assert result.exit_code == 0
    assert "Bread" in result.stdout
