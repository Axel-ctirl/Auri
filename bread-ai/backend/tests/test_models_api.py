"""Model catalogue, load/unload and download gating."""

from __future__ import annotations


def test_builtin_catalogue_is_seeded(client):
    models = client.get("/api/models").json()
    ids = {model["model_id"] for model in models}
    assert "bread/mock" in ids
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in ids
    assert any(model["backend"] == "llama_cpp" for model in models)


def test_load_and_unload_the_mock_backend(client):
    loaded = client.post("/api/models/load", json={"backend": "mock"}).json()
    assert loaded["loaded"] is True
    assert loaded["backend"] == "mock"

    status = client.get("/api/models/status").json()
    assert status["loaded"] is True

    unloaded = client.post("/api/models/unload", json={}).json()
    assert unloaded["loaded"] is False


def test_registering_a_custom_model_then_deleting_it(client):
    registered = client.post(
        "/api/models/register",
        json={
            "name": "My tuned Qwen",
            "model_id": "local/qwen-bread-lora",
            "backend": "transformers",
            "quantization_mode": "4bit",
            "adapter_path": "data/runs/bread-lora",
            "notes": "QLoRA adapter trained on my own plugin code.",
        },
    ).json()
    assert registered["is_builtin"] is False

    assert client.delete(f"/api/models/{registered['id']}").json()["is_builtin"] is False
    assert all(model["id"] != registered["id"] for model in client.get("/api/models").json())


def test_builtin_models_cannot_be_deleted(client):
    builtin = next(
        model for model in client.get("/api/models").json() if model["model_id"] == "bread/mock"
    )
    response = client.delete(f"/api/models/{builtin['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_loading_uncached_weights_without_confirmation_is_refused(client):
    response = client.post(
        "/api/models/load",
        json={"backend": "transformers", "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct"},
    )
    # Either torch is missing or the weights are not cached. Both must be a clean,
    # explained refusal rather than a silent multi-gigabyte download.
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "backend_unavailable"
    assert error["hint"]


def test_chat_without_a_loaded_real_backend_explains_itself(client, bread_env, monkeypatch):
    from app.services.inference import registry

    registry.unload()
    monkeypatch.setattr(bread_env, "model_backend", "transformers")

    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "model_not_loaded"
