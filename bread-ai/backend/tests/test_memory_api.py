"""Memory over HTTP, and memory reaching a chat turn."""

from __future__ import annotations


def test_memory_starts_empty(client):
    assert client.get("/api/memory").json() == []
    stats = client.get("/api/memory/stats").json()
    assert stats["total"] == 0
    assert stats["enabled"] is True


def test_add_list_and_forget(client):
    created = client.post(
        "/api/memory",
        json={"content": "Prefers disnake over discord.py", "kind": "preference"},
    )
    assert created.status_code == 200
    entry_id = created.json()["id"]

    listed = client.get("/api/memory").json()
    assert [item["content"] for item in listed] == ["Prefers disnake over discord.py"]

    assert client.delete(f"/api/memory/{entry_id}").json()["forgotten"] is True
    assert client.delete(f"/api/memory/{entry_id}").status_code == 404


def test_project_scope_needs_a_directory(client):
    response = client.post("/api/memory", json={"content": "note", "scope": "project"})
    assert response.status_code == 422
    assert "project directory" in response.json()["error"]["message"]


def test_a_project_key_is_returned_instead_of_the_path(client, tmp_path):
    response = client.post(
        "/api/memory",
        json={
            "content": "Uses Luau strict mode",
            "scope": "project",
            "project_path": str(tmp_path),
        },
    )
    key = response.json()["project_key"]
    assert key.startswith(f"{tmp_path.name}:")
    assert str(tmp_path) not in key


def test_listing_by_project_includes_global_entries(client, tmp_path):
    client.post("/api/memory", json={"content": "Answers stay short"})
    client.post(
        "/api/memory",
        json={
            "content": "Uses Luau strict mode",
            "scope": "project",
            "project_path": str(tmp_path),
        },
    )
    contents = {
        item["content"]
        for item in client.get("/api/memory", params={"project_path": str(tmp_path)}).json()
    }
    assert contents == {"Answers stay short", "Uses Luau strict mode"}


def test_memory_reaches_the_chat_turn(client):
    client.post("/api/memory", json={"content": "Roblox scripts use Luau strict mode"})
    response = client.post(
        "/api/chat",
        json={"message": "Write me a Roblox script", "persist": False},
    )
    assert response.json()["memory_used"] == ["Roblox scripts use Luau strict mode"]


def test_memory_can_be_turned_off_per_request(client):
    client.post("/api/memory", json={"content": "Roblox scripts use Luau strict mode"})
    response = client.post(
        "/api/chat",
        json={"message": "Write me a Roblox script", "persist": False, "use_memory": False},
    )
    assert response.json()["memory_used"] == []


def test_verification_is_reported_when_asked_for(client):
    response = client.post(
        "/api/chat",
        json={"message": "Read a file", "persist": False, "verify_code": True},
    )
    verification = response.json()["verification"]
    assert verification is not None
    assert verification["problems_remaining"] == 0


def test_verification_is_off_by_default(client):
    response = client.post("/api/chat", json={"message": "Read a file", "persist": False})
    assert response.json()["verification"] is None


def test_the_stream_reports_what_memory_contributed(client):
    client.post("/api/memory", json={"content": "Roblox scripts use Luau strict mode"})
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "Write me a Roblox script", "persist": False}
    ) as response:
        meta = next(line for line in response.iter_lines() if line.startswith("data: "))
    assert "Luau strict mode" in meta
