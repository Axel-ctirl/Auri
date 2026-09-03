"""API keys, rate limiting and the LAN-binding guard."""

from __future__ import annotations

import pytest


def test_key_is_returned_once_and_stored_hashed(client, session):
    from app.models import ApiKey

    created = client.post("/api/api-keys", json={"label": "laptop"}).json()
    assert created["key"].startswith("bread_sk_")
    assert created["key_prefix"] in created["key"]

    stored = session.get(ApiKey, created["id"])
    assert stored is not None
    assert stored.key_hash != created["key"]
    assert created["key"] not in stored.key_hash


def test_listing_keys_never_leaks_the_hash(client):
    client.post("/api/api-keys", json={"label": "ci"})
    listed = client.get("/api/api-keys").json()
    assert listed
    assert "key_hash" not in listed[0]
    assert "key" not in listed[0]


def test_revoked_key_is_rejected(bread_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as open_client:
        created = open_client.post("/api/api-keys", json={"label": "temp"}).json()
        open_client.delete(f"/api/api-keys/{created['id']}")

    monkeypatch.setattr(bread_env, "require_api_key", True)
    with TestClient(create_app()) as guarded:
        response = guarded.get("/api/conversations", headers={"X-API-Key": created["key"]})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


def test_enforced_mode_requires_a_key_but_leaves_health_open(bread_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as open_client:
        created = open_client.post("/api/api-keys", json={"label": "lan"}).json()

    monkeypatch.setattr(bread_env, "require_api_key", True)
    with TestClient(create_app()) as guarded:
        assert guarded.get("/api/health").status_code == 200
        assert guarded.get("/api/conversations").status_code == 401
        assert (
            guarded.get("/api/conversations", headers={"X-API-Key": created["key"]}).status_code
            == 200
        )
        assert (
            guarded.get(
                "/api/conversations",
                headers={"Authorization": f"Bearer {created['key']}"},
            ).status_code
            == 200
        )


def test_rate_limiter_blocks_a_burst(bread_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setattr(bread_env, "rate_limit_requests", 5)
    monkeypatch.setattr(bread_env, "rate_limit_window_seconds", 60)

    with TestClient(create_app()) as limited:
        codes = [limited.get("/api/conversations").status_code for _ in range(8)]

    assert codes.count(200) == 5
    assert codes[-1] == 429


def test_lan_binding_produces_warnings_and_forces_key_checks(bread_env, monkeypatch):
    from app.security import ensure_lan_guard

    monkeypatch.setattr(bread_env, "host", "0.0.0.0")
    warnings = ensure_lan_guard(bread_env)
    assert warnings
    assert any("reachable from your network" in warning for warning in warnings)
    assert bread_env.binds_to_lan is True


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", False),
        ("localhost", False),
        ("::1", False),
        ("192.168.1.20", True),
    ],
)
def test_lan_detection(bread_env, monkeypatch, host, expected):
    monkeypatch.setattr(bread_env, "host", host)
    assert bread_env.binds_to_lan is expected


def test_audit_log_records_state_changing_actions(client):
    space = client.post("/api/knowledge-spaces", json={"name": "Audited"}).json()
    client.delete(f"/api/knowledge-spaces/{space['id']}")
    client.post("/api/models/load", json={"backend": "mock"})

    entries = client.get("/api/audit-logs").json()
    actions = [entry["action"] for entry in entries]

    assert "knowledge_space.create" in actions
    assert "knowledge_space.delete" in actions
    assert "model.load" in actions

    creation = next(entry for entry in entries if entry["action"] == "knowledge_space.create")
    assert creation["target_id"] == space["id"]
    assert creation["detail"]["name"] == "Audited"


def test_audit_log_is_newest_first_and_respects_the_limit(client):
    for index in range(4):
        client.post("/api/knowledge-spaces", json={"name": f"Space {index}"})

    entries = client.get("/api/audit-logs", params={"limit": 2}).json()
    assert len(entries) == 2
    assert entries[0]["created_at"] >= entries[1]["created_at"]
