"""Health, status and OpenAPI surface."""

from __future__ import annotations


def test_health_reports_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Bread"


def test_system_status_includes_model_and_gpu(client):
    body = client.get("/api/system/status").json()
    assert body["model"]["backend"] in {"none", "mock"}
    assert "cuda_available" in body["gpu"]
    assert body["binds_to_lan"] is False
    assert isinstance(body["optional_dependencies"], dict)


def test_gpu_endpoint_survives_a_machine_without_cuda(client):
    body = client.get("/api/system/gpu").json()
    assert isinstance(body["cuda_available"], bool)
    assert isinstance(body["devices"], list)


def test_openapi_documents_every_endpoint_group(client):
    paths = client.get("/openapi.json").json()["paths"]
    for expected in (
        "/api/chat",
        "/api/chat/stream",
        "/api/conversations",
        "/api/knowledge-spaces",
        "/api/documents/upload",
        "/api/rag/search",
        "/api/datasets/collect",
        "/api/training/start",
        "/api/settings",
        "/api/api-keys",
    ):
        assert expected in paths, f"{expected} is missing from the OpenAPI schema"


def test_unknown_route_returns_structured_error(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert "error" in response.json()
