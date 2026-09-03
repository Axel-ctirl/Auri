"""Conversation CRUD, search and rollback."""

from __future__ import annotations


def test_create_list_rename_and_delete(client):
    created = client.post("/api/conversations", json={"title": "Paper plugin work"}).json()
    assert created["title"] == "Paper plugin work"

    listed = client.get("/api/conversations").json()
    assert any(item["id"] == created["id"] for item in listed)

    renamed = client.patch(
        f"/api/conversations/{created['id']}",
        json={"title": "Fabric mod work", "pinned": True},
    ).json()
    assert renamed["title"] == "Fabric mod work"
    assert renamed["pinned"] is True

    assert client.delete(f"/api/conversations/{created['id']}").json()["deleted"] is True
    assert client.get(f"/api/conversations/{created['id']}").status_code == 404


def test_search_filters_by_title(client):
    client.post("/api/conversations", json={"title": "Discord bot in Python"})
    client.post("/api/conversations", json={"title": "Rust ownership questions"})

    results = client.get("/api/conversations", params={"search": "discord"}).json()
    assert len(results) == 1
    assert results[0]["title"] == "Discord bot in Python"


def test_archived_conversations_are_hidden_by_default(client):
    created = client.post("/api/conversations", json={"title": "Old thread"}).json()
    client.patch(f"/api/conversations/{created['id']}", json={"archived": True})

    assert all(item["id"] != created["id"] for item in client.get("/api/conversations").json())
    with_archived = client.get("/api/conversations", params={"include_archived": True}).json()
    assert any(item["id"] == created["id"] for item in with_archived)


def test_rollback_drops_the_reply_so_it_can_be_regenerated(client):
    first = client.post("/api/chat", json={"message": "Generate a Go HTTP handler."}).json()
    detail = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assistant_message = detail["messages"][-1]

    rolled_back = client.post(
        f"/api/conversations/{first['conversation_id']}"
        f"/messages/{assistant_message['id']}/rollback"
    ).json()
    assert [message["role"] for message in rolled_back["messages"]] == ["user"]


def test_message_count_and_preview_are_reported(client):
    body = client.post("/api/chat", json={"message": "Explain SQL window functions."}).json()
    summary = next(
        item
        for item in client.get("/api/conversations").json()
        if item["id"] == body["conversation_id"]
    )
    assert summary["message_count"] == 2
    assert summary["last_message_preview"]


def test_missing_conversation_returns_structured_404(client):
    response = client.get("/api/conversations/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
