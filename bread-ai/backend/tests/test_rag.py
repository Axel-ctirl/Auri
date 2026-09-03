"""Uploads, indexing, retrieval and the safety rules around them."""

from __future__ import annotations

import io


def _upload(client, name: str, content: str, space_id: str | None = None):
    data = {"index_now": "true"}
    if space_id:
        data["knowledge_space_id"] = space_id
    return client.post(
        "/api/documents/upload",
        files={"files": (name, io.BytesIO(content.encode("utf-8")), "text/plain")},
        data=data,
    )


PAPER_PLUGIN = """
package com.example.bread;

import org.bukkit.plugin.java.JavaPlugin;

public final class BreadPlugin extends JavaPlugin {
    @Override
    public void onEnable() {
        getLogger().info("Bread plugin enabled");
        getCommand("bread").setExecutor(new BreadCommand());
    }
}
"""

LUAU_SCRIPT = """
local AntiSpeed = {}

function AntiSpeed.isMovingTooFast(player, maxStudsPerSecond)
    local character = player.Character
    return character.PrimaryPart.AssemblyLinearVelocity.Magnitude > maxStudsPerSecond
end

return AntiSpeed
"""


def test_upload_and_index_then_search_finds_the_right_document(client):
    assert _upload(client, "BreadPlugin.java", PAPER_PLUGIN).status_code == 200
    assert _upload(client, "AntiSpeed.luau", LUAU_SCRIPT).status_code == 200

    documents = client.get("/api/documents").json()
    assert len(documents) == 2
    assert all(document["status"] == "indexed" for document in documents)
    assert all(document["chunk_count"] > 0 for document in documents)

    results = client.post(
        "/api/rag/search", json={"query": "AssemblyLinearVelocity anti speed check", "top_k": 2}
    ).json()
    assert results["results"]
    assert results["results"][0]["document_name"] == "AntiSpeed.luau"
    assert results["results"][0]["chunk_index"] >= 0
    assert results["results"][0]["excerpt"]


def test_identical_content_is_skipped_on_re_upload(client):
    _upload(client, "same.py", "def add(a, b):\n    return a + b\n" * 5)
    second = _upload(client, "same.py", "def add(a, b):\n    return a + b\n" * 5).json()
    assert second["documents"] == []
    assert "already indexed" in second["skipped"][0]["reason"]


def test_unsupported_extension_is_rejected_not_crashed(client):
    response = _upload(client, "payload.exe", "MZ binary junk")
    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == []
    assert "does not index" in body["skipped"][0]["reason"]


def test_path_traversal_filename_is_sanitised(client, bread_env):
    response = _upload(client, "../../../etc/passwd.txt", "root:x:0:0" * 40)
    body = response.json()
    assert body["documents"], body
    stored_name = body["documents"][0]["filename"]
    assert "/" not in stored_name and ".." not in stored_name

    uploads = list(bread_env.uploads_dir.iterdir())
    assert all(path.parent == bread_env.uploads_dir for path in uploads)


def test_oversized_upload_is_refused(client, bread_env, monkeypatch):
    monkeypatch.setattr(bread_env, "max_upload_bytes", 100)
    body = _upload(client, "big.txt", "x" * 5000).json()
    assert body["documents"] == []
    assert "limit is" in body["skipped"][0]["reason"]


def test_deleting_a_document_removes_its_chunks_and_vectors(client):
    uploaded = _upload(client, "todelete.py", "def compute_total(rows):\n    return sum(rows)\n" * 6)
    document_id = uploaded.json()["documents"][0]["id"]

    assert client.delete(f"/api/documents/{document_id}").json()["deleted"] is True
    assert client.get("/api/documents").json() == []

    results = client.post("/api/rag/search", json={"query": "compute_total"}).json()
    assert results["results"] == []


def test_knowledge_spaces_isolate_their_documents(client):
    space = client.post(
        "/api/knowledge-spaces",
        json={"name": "Roblox Luau Docs", "description": "Luau reference"},
    ).json()
    _upload(client, "isolated.luau", LUAU_SCRIPT, space_id=space["id"])

    in_space = client.get("/api/documents", params={"knowledge_space_id": space["id"]}).json()
    assert len(in_space) == 1

    default_space = client.get("/api/knowledge-spaces").json()[0]
    hits = client.post(
        "/api/rag/search",
        json={"query": "AssemblyLinearVelocity", "knowledge_space_id": default_space["id"]},
    ).json()
    assert hits["results"] == []


def test_chat_with_rag_returns_citations(client):
    _upload(client, "BreadPlugin.java", PAPER_PLUGIN)
    body = client.post(
        "/api/chat",
        json={"message": "What does BreadPlugin.onEnable do?", "rag_enabled": True},
    ).json()
    assert body["sources"]
    assert body["sources"][0]["document_name"] == "BreadPlugin.java"


def test_deleting_a_space_removes_its_documents(client):
    space = client.post("/api/knowledge-spaces", json={"name": "Scratch"}).json()
    _upload(client, "scratch.py", "def scratch():\n    return 1\n" * 8, space_id=space["id"])

    assert client.delete(f"/api/knowledge-spaces/{space['id']}").json()["deleted"] is True
    assert client.get("/api/documents", params={"knowledge_space_id": space["id"]}).json() == []
