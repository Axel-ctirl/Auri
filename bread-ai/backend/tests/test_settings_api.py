"""Runtime settings and prompt presets."""

from __future__ import annotations


def test_settings_expose_the_effective_configuration(client):
    body = client.get("/api/settings").json()
    assert body["model_backend"] == "mock"
    assert body["rag_top_k"] >= 1
    assert body["data_dir"]


def test_updating_settings_persists_and_applies(client):
    updated = client.patch(
        "/api/settings", json={"temperature": 0.7, "rag_top_k": 9, "rag_enabled": False}
    ).json()
    assert updated["temperature"] == 0.7
    assert updated["rag_top_k"] == 9
    assert updated["rag_enabled"] is False

    assert client.get("/api/settings").json()["temperature"] == 0.7


def test_settings_reject_out_of_range_values(client):
    response = client.patch("/api/settings", json={"temperature": 12})
    assert response.status_code == 422


def test_network_settings_are_not_editable_over_http(client):
    before = client.get("/api/settings").json()["host"]
    client.patch("/api/settings", json={"host": "0.0.0.0", "require_api_key": False})
    assert client.get("/api/settings").json()["host"] == before


def test_prompt_presets_are_listed_and_fetchable(client):
    presets = client.get("/api/prompts/presets").json()
    names = {preset["name"] for preset in presets}
    assert "minecraft_paper_plugin" in names
    assert "roblox_luau_game" in names

    one = client.get("/api/prompts/presets/minecraft_paper_plugin").json()
    assert one["title"]
    assert one["body"]


def test_unknown_preset_is_a_clean_404(client):
    assert client.get("/api/prompts/presets/not_a_preset").status_code == 404


def test_chat_accepts_a_preset(client):
    response = client.post(
        "/api/chat",
        json={"message": "Add a /kit command.", "preset": "minecraft_paper_plugin"},
    )
    assert response.status_code == 200
