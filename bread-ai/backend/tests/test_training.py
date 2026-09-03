"""Training run bookkeeping and preflight checks.

No test here starts a real fine-tune: the suite must run on a machine with no
GPU. The dry-run path is exactly what a user should run first anyway.
"""

from __future__ import annotations


def test_shipped_configs_are_listed(client):
    configs = client.get("/api/training/configs").json()
    names = {config["name"] for config in configs}
    assert {"qlora_7b", "qlora_14b", "lora_small_fallback", "tiny_scratch"} <= names

    qlora = next(config for config in configs if config["name"] == "qlora_7b")
    assert qlora["base_model_id"].startswith("Qwen/")
    assert qlora["min_vram_gb"]


def test_dry_run_reports_problems_without_starting_anything(client):
    run = client.post(
        "/api/training/start",
        json={
            "name": "dry run check",
            "config_path": "configs/training/qlora_7b.yaml",
            "dataset_path": "data/datasets/does-not-exist.jsonl",
            "dry_run": True,
        },
    ).json()

    assert run["status"] in {"completed", "failed"}
    assert run["pid"] is None
    if run["status"] == "failed":
        assert "not found" in run["error"] or "not installed" in run["error"]


def test_config_paths_outside_the_repo_are_refused(client):
    response = client.post(
        "/api/training/start",
        json={"name": "escape", "config_path": "/etc/shadow", "dry_run": True},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "config_outside_repo"


def test_missing_config_is_a_clean_404(client):
    response = client.post(
        "/api/training/start",
        json={
            "name": "nope",
            "config_path": "configs/training/nope.yaml",
            "dry_run": True,
        },
    )
    assert response.status_code == 404


def test_runs_are_listed_and_fetchable(client):
    started = client.post(
        "/api/training/start",
        json={
            "name": "listed run",
            "config_path": "configs/training/lora_small_fallback.yaml",
            "dry_run": True,
        },
    ).json()

    runs = client.get("/api/training/runs").json()
    assert any(run["id"] == started["id"] for run in runs)

    fetched = client.get(f"/api/training/{started['id']}").json()
    assert fetched["name"] == "listed run"
    assert fetched["config_path"].endswith("lora_small_fallback.yaml")

    logs = client.get(f"/api/training/{started['id']}/logs").json()
    assert logs["run_id"] == started["id"]
    assert logs["lines"] == []


def test_stopping_a_run_that_is_not_running_conflicts(client):
    started = client.post(
        "/api/training/start",
        json={
            "name": "already finished",
            "config_path": "configs/training/tiny_scratch.yaml",
            "dry_run": True,
        },
    ).json()

    response = client.post("/api/training/stop", json={"run_id": started["id"]})
    assert response.status_code == 409


def test_preflight_flags_a_missing_dataset(bread_env):
    from pathlib import Path

    from app.services.training_service import (
        load_config,
        preflight,
        resolve_config_path,
    )

    config = load_config(resolve_config_path("configs/training/qlora_7b.yaml"))
    problems = preflight(config, Path("/definitely/not/here.jsonl"))
    assert any("Dataset file not found" in problem for problem in problems)
