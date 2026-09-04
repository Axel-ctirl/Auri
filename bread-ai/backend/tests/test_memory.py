"""Memory: what Bread carries between conversations, and what it leaves behind."""

from __future__ import annotations

import pytest

from app.services import memory as memory_service


def test_remember_normalises_and_deduplicates(session):
    first = memory_service.remember(session, "  Use  tabs   in Lua \n")
    assert first.content == "Use tabs in Lua"

    again = memory_service.remember(session, "Use tabs in Lua", pinned=True)
    assert again.id == first.id
    # Re-remembering something is a signal it matters, not a second row.
    assert again.pinned is True
    assert len(memory_service.list_entries(session)) == 1


def test_remember_rejects_bad_input(session):
    with pytest.raises(ValueError):
        memory_service.remember(session, "   ")
    with pytest.raises(ValueError):
        memory_service.remember(session, "text", kind="opinion")
    with pytest.raises(ValueError):
        memory_service.remember(session, "text", scope="project")


def test_content_is_truncated_not_rejected(session):
    entry = memory_service.remember(session, "x" * 5000)
    assert len(entry.content) <= memory_service.MAX_CONTENT_CHARS


def test_project_key_hides_the_path_but_keeps_the_name(tmp_path):
    key = memory_service.project_key(tmp_path)
    assert key is not None
    assert key.startswith(f"{tmp_path.name}:")
    assert str(tmp_path) not in key
    assert memory_service.project_key(None) is None


def test_project_scope_does_not_leak_between_projects(session, tmp_path):
    here = tmp_path / "here"
    elsewhere = tmp_path / "elsewhere"
    here.mkdir()
    elsewhere.mkdir()

    memory_service.remember(
        session, "This project pins disnake 2.12.1", scope="project", project=here
    )
    memory_service.remember(session, "Prefers disnake over discord.py", scope="global")

    from_here = [entry.content for entry in memory_service.recall(session, "disnake", project=here)]
    assert "This project pins disnake 2.12.1" in from_here

    from_elsewhere = [
        entry.content for entry in memory_service.recall(session, "disnake", project=elsewhere)
    ]
    assert "This project pins disnake 2.12.1" not in from_elsewhere
    assert "Prefers disnake over discord.py" in from_elsewhere


def test_recall_ignores_common_words(session):
    memory_service.remember(session, "The build uses a Makefile")
    assert memory_service.recall(session, "What is a linear equation?") == []


def test_pinned_entries_are_always_recalled(session):
    memory_service.remember(session, "Answer in British English", pinned=True)
    recalled = memory_service.recall(session, "something entirely unrelated")
    assert [entry.content for entry in recalled] == ["Answer in British English"]


def test_recall_counts_uses(session):
    entry = memory_service.remember(session, "Roblox scripts use Luau strict mode")
    memory_service.recall(session, "How do I write a Roblox script?")
    session.refresh(entry)
    assert entry.use_count == 1
    assert entry.last_used_at is not None


def test_corrections_outrank_facts_at_equal_overlap(session):
    memory_service.remember(session, "disnake timeout uses a duration", kind="fact")
    memory_service.remember(session, "disnake timeout uses a duration too", kind="correction")
    recalled = memory_service.recall(session, "disnake timeout duration", limit=2)
    assert recalled[0].kind == "correction"


def test_recall_limit_is_respected(session):
    for index in range(20):
        memory_service.remember(session, f"disnake detail number {index}")
    assert len(memory_service.recall(session, "disnake detail", limit=4)) == 4


def test_render_marks_memory_as_context_not_instruction(session):
    memory_service.remember(session, "Prefers short answers", kind="preference")
    block = memory_service.render_for_prompt(memory_service.recall(session, "short answers"))
    assert "Prefers short answers" in block
    assert "context rather than as instruction" in block


def test_render_of_nothing_is_empty():
    assert memory_service.render_for_prompt([]) == ""


def test_augment_leaves_the_prompt_alone_when_nothing_matches(session):
    prompt, entries = memory_service.augment_system_prompt(session, "BASE", "unmatched question")
    assert prompt == "BASE"
    assert entries == []


def test_forget_removes_one_entry(session):
    entry = memory_service.remember(session, "Temporary note")
    assert memory_service.forget(session, entry.id) is True
    assert memory_service.forget(session, entry.id) is False
    assert memory_service.list_entries(session) == []
