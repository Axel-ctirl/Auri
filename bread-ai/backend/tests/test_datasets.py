"""Dataset collection, licensing gates, validation and reporting."""

from __future__ import annotations

import json
import time

MIT_LICENSE = """MIT License

Copyright (c) 2026 Example

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""

GPL_LICENSE = """GNU GENERAL PUBLIC LICENSE
Version 3, 29 June 2007

Everyone is permitted to copy and distribute verbatim copies of this license
document, but changing it is not allowed.
"""

SAMPLE_MODULE = '''"""Inventory helpers for the shop plugin."""


def calculate_restock_quantity(current_stock, reorder_point, target_stock):
    """Return how many units to order so stock reaches the target level."""

    if current_stock >= reorder_point:
        return 0
    return max(target_stock - current_stock, 0)


def format_currency(amount_in_cents, currency_symbol="$"):
    """Render an integer number of cents as a human-readable amount."""

    return f"{currency_symbol}{amount_in_cents / 100:.2f}"
'''

LEAKY_MODULE = '''import requests

GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def fetch_issues(repository):
    return requests.get(
        f"https://api.github.com/repos/{repository}/issues",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
    ).json()
'''


def _make_repo(root, name, license_text, files):
    repo = root / name
    repo.mkdir(parents=True)
    (repo / "LICENSE").write_text(license_text, encoding="utf-8")
    for filename, content in files.items():
        target = repo / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return repo


def _wait_for_run(client, run_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/api/datasets").json()
        run = next((item for item in runs if item["id"] == run_id), None)
        if run and run["status"] in {"completed", "failed"}:
            return run
        time.sleep(0.05)
    raise AssertionError("The collection run never finished.")


def test_local_collection_keeps_permissive_code_and_skips_copyleft(client, tmp_path):
    workspace = tmp_path / "projects"
    _make_repo(workspace, "shop-plugin", MIT_LICENSE, {"inventory.py": SAMPLE_MODULE})
    _make_repo(workspace, "gpl-tool", GPL_LICENSE, {"tool.py": SAMPLE_MODULE})

    started = client.post(
        "/api/datasets/collect",
        json={
            "name": "local starter",
            "source": "local_code",
            "input_paths": [str(workspace)],
            "languages": ["python"],
            "max_records": 50,
        },
    ).json()

    run = _wait_for_run(client, started["id"])
    assert run["status"] == "completed", run["error"]
    assert run["record_count"] == 1

    report = client.get("/api/datasets/report", params={"path": run["output_path"]}).json()
    assert report["total_records"] == 1
    assert report["license_counts"] == {"MIT": 1}
    assert report["language_counts"] == {"python": 1}
    assert any("license" in warning.lower() for warning in report["warnings"])


def test_files_containing_credentials_are_left_out(client, tmp_path):
    workspace = tmp_path / "projects"
    _make_repo(
        workspace,
        "leaky",
        MIT_LICENSE,
        {"safe.py": SAMPLE_MODULE, "leaky.py": LEAKY_MODULE},
    )

    started = client.post(
        "/api/datasets/collect",
        json={
            "name": "secret scan",
            "source": "local_code",
            "input_paths": [str(workspace)],
            "languages": ["python"],
        },
    ).json()
    run = _wait_for_run(client, started["id"])

    assert run["record_count"] == 1
    contents = open(run["output_path"], encoding="utf-8").read()
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in contents


def test_manifest_records_provenance(client, tmp_path):
    workspace = tmp_path / "projects"
    _make_repo(workspace, "shop-plugin", MIT_LICENSE, {"inventory.py": SAMPLE_MODULE})

    started = client.post(
        "/api/datasets/collect",
        json={
            "name": "manifest check",
            "source": "local_code",
            "input_paths": [str(workspace)],
            "languages": ["python"],
        },
    ).json()
    run = _wait_for_run(client, started["id"])

    manifest = json.loads(run["manifest_json"] or "{}")
    assert manifest["source"] == "local_code"
    assert manifest["license_summary"] == {"MIT": 1}
    assert manifest["warnings"]
    assert manifest["collected_at"]


def test_external_source_requires_explicit_terms_acceptance(client):
    response = client.post(
        "/api/datasets/collect",
        json={"name": "stack sample", "source": "the_stack", "max_records": 10},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "terms_not_accepted"
    assert error["details"]["terms_url"]


def test_sources_endpoint_lists_terms_urls(client):
    body = client.get("/api/datasets/sources").json()
    assert {item["id"] for item in body["local"]} == {"local_code", "local_english"}
    assert all(item["requires_terms"] for item in body["external"])
    assert all(item["terms_url"] for item in body["external"])
    assert "never scrapes websites" in body["notice"]


def test_validation_reports_bad_records(client, bread_env):
    dataset = bread_env.datasets_path / "broken.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Explain closures in JavaScript."},
                            {"role": "assistant", "content": "A closure captures scope."},
                        ]
                    }
                ),
                json.dumps({"messages": [{"role": "user", "content": ""}]}),
                "{not json at all",
            ]
        ),
        encoding="utf-8",
    )

    body = client.post(
        "/api/datasets/validate", json={"path": str(dataset), "schema_name": "sft_chat"}
    ).json()
    assert body["total_records"] == 3
    assert body["valid_records"] == 1
    assert body["invalid_records"] == 2
    assert body["issues"]


def test_dataset_paths_outside_the_data_directory_are_refused(client):
    response = client.get("/api/datasets/report", params={"path": "/etc/passwd"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "path_outside_data_dir"


def test_unsupported_language_is_rejected(client, tmp_path):
    response = client.post(
        "/api/datasets/collect",
        json={
            "name": "bad languages",
            "source": "local_code",
            "input_paths": [str(tmp_path)],
            "languages": ["cobol"],
        },
    )
    assert response.status_code == 422
    assert "cobol" in response.json()["error"]["message"]
