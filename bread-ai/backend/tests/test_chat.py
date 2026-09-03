"""Chat, streaming, persistence and stop."""

from __future__ import annotations

import json


def test_chat_creates_a_conversation_and_persists_both_messages(client):
    response = client.post("/api/chat", json={"message": "Explain this Python function."})
    assert response.status_code == 200
    body = response.json()
    assert body["content"]
    assert body["backend"] == "mock"

    detail = client.get(f"/api/conversations/{body['conversation_id']}").json()
    roles = [message["role"] for message in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["title"].startswith("Explain this Python function")


def test_chat_continues_an_existing_conversation(client):
    first = client.post("/api/chat", json={"message": "First question about Rust."}).json()
    client.post(
        "/api/chat",
        json={"conversation_id": first["conversation_id"], "message": "And a follow-up."},
    )
    detail = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assert len(detail["messages"]) == 4


def test_chat_respects_persist_false(client):
    body = client.post(
        "/api/chat", json={"message": "Do not store this.", "persist": False}
    ).json()
    detail = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert detail["messages"] == []


def test_stream_emits_meta_tokens_and_done(client):
    with client.stream(
        "POST", "/api/chat/stream", json={"message": "Write a TypeScript retry helper."}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.iter_lines())

    kinds = [event for event, _ in events]
    assert kinds[0] == "meta"
    assert "token" in kinds
    assert kinds[-1] == "done"

    text = "".join(payload["delta"] for kind, payload in events if kind == "token")
    assert "Mock backend" in text

    done_payload = events[-1][1]
    assert done_payload["message_id"]
    assert done_payload["error"] is None


def test_stop_reports_when_nothing_is_running(client):
    body = client.post("/api/chat/stop", json={}).json()
    assert body["stopped"] is False
    assert body["stream_ids"] == []


def test_generation_parameters_are_accepted(client):
    response = client.post(
        "/api/chat",
        json={
            "message": "Refactor this Java class.",
            "temperature": 0.0,
            "top_p": 0.5,
            "max_new_tokens": 64,
        },
    )
    assert response.status_code == 200


def test_out_of_range_temperature_is_rejected(client):
    response = client.post("/api/chat", json={"message": "hi", "temperature": 9})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def _parse_sse(lines) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    current_event = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:") and current_event:
            events.append((current_event, json.loads(line[5:].strip())))
            current_event = None
    return events
