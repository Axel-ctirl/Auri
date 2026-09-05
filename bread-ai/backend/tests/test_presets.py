"""Presets: choosing the right one, and shipping examples that actually run."""

from __future__ import annotations

import asyncio
import importlib.util
import sys

import pytest

from app.config import REPO_ROOT
from app.services.prompts import compose_system_prompt, get_preset, list_presets, suggest
from app.services.quality.api_check import check_code

PRESET_DIR = REPO_ROOT / "prompts" / "presets"


def test_every_preset_declares_what_selects_it():
    for preset in list_presets():
        assert preset["triggers"], f"{preset['name']} has no Triggers line"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Write a Discord bot with disnake that records messages", "discord_bot_python"),
        ("build a fastapi endpoint that returns users", "fastapi_project"),
        ("design a rest api for a todo list", "rest_api"),
        ("make a paper plugin for minecraft", "minecraft_paper_plugin"),
        ("write a roblox luau script for a leaderboard", "roblox_luau_game"),
        ("a react component with a hook", "react_project"),
        ("write a dockerfile for this project", "docker_project"),
    ],
)
def test_a_question_selects_its_preset(question, expected):
    assert suggest(question) == expected


@pytest.mark.parametrize(
    "question",
    ["what is a linear equation", "reverse a linked list in python", ""],
)
def test_an_unrelated_question_selects_nothing(question):
    """A preset applied to the wrong question is worse than no preset."""

    assert suggest(question) is None


def test_the_preset_and_its_example_reach_the_prompt():
    prompt = compose_system_prompt("BASE", "discord_bot_python")
    assert prompt.startswith("BASE")
    assert "Python Discord bot" in prompt
    assert "discord_bot_python.reference.py" in prompt
    assert "message_content" in prompt


def test_the_example_can_be_left_out():
    prompt = compose_system_prompt("BASE", "discord_bot_python", include_reference=False)
    assert "reference.py" not in prompt


def test_no_preset_leaves_the_prompt_alone():
    assert compose_system_prompt("BASE") == "BASE"


def _reference_files():
    return sorted(PRESET_DIR.glob("*.reference.py"))


def test_there_is_at_least_one_worked_example():
    assert _reference_files()


@pytest.mark.parametrize("path", _reference_files(), ids=lambda path: path.name)
def test_every_python_example_passes_the_same_check_a_model_answer_gets(path):
    """An example that does not survive Bread's own checker teaches the wrong thing."""

    report = check_code(path.read_text(encoding="utf-8"), allow_import=True)
    assert report.ok, [finding.message for finding in report.certain]
    assert not report.likely, [finding.message for finding in report.likely]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Pydantic resolves postponed annotations through sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_discord_example_actually_works():
    disnake = pytest.importorskip("disnake")
    assert disnake  # the reference imports it at module level
    module = _load(PRESET_DIR / "discord_bot_python.reference.py", "bread_ref_discord")

    class Author:
        def __init__(self, is_bot):
            self.bot = is_bot

    class Channel:
        def __init__(self, channel_id):
            self.id = channel_id

    class Message:
        def __init__(self, content, channel_id, is_bot=False):
            self.content = content
            self.channel = Channel(channel_id)
            self.author = Author(is_bot)

    sent = {}

    class Response:
        async def send_message(self, content=None, **kwargs):
            sent.update(content=content, kwargs=kwargs)

    class Interaction:
        def __init__(self, channel_id):
            self.channel_id = channel_id
            self.response = Response()

    async def exercise():
        for text, channel_id, is_bot in [
            ("hello", 1, False),
            ("world", 1, False),
            ("beep", 1, True),
            ("   ", 1, False),
            ("elsewhere", 2, False),
        ]:
            await module.on_message(Message(text, channel_id, is_bot))

        # Bots and empty messages are skipped, and channels do not mix.
        assert list(module.recorded[1]) == ["hello", "world"]
        assert list(module.recorded[2]) == ["elsewhere"]

        await module.random_message.callback(Interaction(1))
        assert sent["content"] in ("> hello", "> world")
        # Quoting text verbatim must not let anyone make the bot ping @everyone.
        assert sent["kwargs"]["allowed_mentions"].everyone is False

        await module.random_message.callback(Interaction(999))
        assert sent["kwargs"]["ephemeral"] is True

        await module.remembered.callback(Interaction(1))
        assert sent["content"] == "2 message(s) from this channel."

    asyncio.run(exercise())

    # The history is bounded, so a busy server cannot grow it without limit.
    module.recorded[3].extend(str(number) for number in range(module.HISTORY_LIMIT + 50))
    assert len(module.recorded[3]) == module.HISTORY_LIMIT


def test_the_fastapi_example_actually_serves_requests():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    module = _load(PRESET_DIR / "fastapi_project.reference.py", "bread_ref_fastapi")
    client = TestClient(module.create_app())

    assert client.get("/health").json() == {"status": "ok"}
    created = client.post("/notes", json={"title": "first", "body": "hello"})
    assert created.status_code == 201
    note_id = created.json()["id"]

    page = client.get("/notes").json()
    assert page["total"] == 1 and page["limit"] == 20

    assert client.get(f"/notes/{note_id}").status_code == 200
    assert client.get("/notes/9999").status_code == 404
    assert client.delete(f"/notes/{note_id}").status_code == 204
    assert client.delete(f"/notes/{note_id}").status_code == 404
    assert client.post("/notes", json={"title": ""}).status_code == 422


def test_an_unknown_preset_is_a_clear_error():
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        get_preset("no_such_preset")


def test_auto_selects_a_preset_over_http(client):
    """A caller with no dropdown can ask Bread to pick."""

    from app.services import chat_service

    seen: dict[str, str] = {}
    original = chat_service.compose_system_prompt

    def spy(base, preset_name=None, **kwargs):
        seen["preset"] = preset_name or ""
        return original(base, preset_name, **kwargs)

    chat_service.compose_system_prompt = spy
    try:
        response = client.post(
            "/api/chat",
            json={
                "message": "write a disnake bot with a slash command",
                "preset": "auto",
                "persist": False,
            },
        )
    finally:
        chat_service.compose_system_prompt = original

    assert response.status_code == 200
    assert seen["preset"] == "discord_bot_python"


def test_an_unrelated_question_gets_no_preset_over_http(client):
    from app.services import chat_service

    seen: dict[str, str] = {}
    original = chat_service.compose_system_prompt

    def spy(base, preset_name=None, **kwargs):
        seen["preset"] = preset_name or ""
        return original(base, preset_name, **kwargs)

    chat_service.compose_system_prompt = spy
    try:
        client.post(
            "/api/chat",
            json={"message": "what is a linear equation", "preset": "auto", "persist": False},
        )
    finally:
        chat_service.compose_system_prompt = original

    assert seen["preset"] == ""
