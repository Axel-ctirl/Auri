"""End-to-end checks for the command-line pipeline.

These run the scripts as modules in-process, which keeps them fast and still
exercises the argument parsing users actually type.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

MIT_LICENSE = (
    "MIT License\n\nPermission is hereby granted, free of charge, to any person "
    "obtaining a copy of this software.\n"
)

MODULE_TEMPLATE = '''"""Inventory helpers, module {index}."""


def calculate_restock_quantity_{index}(current_stock, reorder_point, target_stock):
    """Return how many units to order so stock reaches the target level.

    Returns zero when current stock is already at or above the reorder point.
    """

    if current_stock >= reorder_point:
        return 0
    return max(target_stock - current_stock, 0)


def summarize_orders_{index}(orders):
    """Total a list of orders and report how many there were.

    Amounts stay in whole cents so no rounding happens before display.
    """

    total = sum(order["amount_in_cents"] for order in orders)
    return {{"count": len(orders), "total_cents": total}}
'''


def load_script(name: str):
    """Import a script by path, with the scripts directory on sys.path."""

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"bread_script_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def sample_project(tmp_path):
    project = tmp_path / "inventory-service"
    project.mkdir()
    (project / "LICENSE").write_text(MIT_LICENSE, encoding="utf-8")
    for index in range(6):
        (project / f"module_{index}.py").write_text(
            MODULE_TEMPLATE.format(index=index), encoding="utf-8"
        )
    return project


def test_license_check_reports_the_project(sample_project, capsys):
    exit_code = load_script("license_check").main(["--path", str(sample_project.parent)])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "MIT" in output
    assert "collect" in output


def test_full_pipeline_from_collection_to_training_file(sample_project, tmp_path, capsys):
    raw = tmp_path / "raw.jsonl"
    exit_code = load_script("collect_local_code").main(
        [
            "--path",
            str(sample_project),
            "--name",
            "pipeline",
            "--output",
            str(raw),
            "--languages",
            "python",
        ]
    )
    capsys.readouterr()
    assert exit_code == 0
    assert raw.exists()

    manifest = json.loads(raw.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["license_summary"] == {"MIT": 6}
    assert manifest["warnings"]
    # Six files, two documented functions each, three tasks per function.
    assert manifest["configuration"]["extraction"]["units_accepted"] == 12

    cleaned = tmp_path / "clean.jsonl"
    assert load_script("clean_dataset").main(["--input", str(raw), "--output", str(cleaned)]) == 0
    capsys.readouterr()

    assert load_script("validate_dataset").main(["--input", str(cleaned)]) == 0
    capsys.readouterr()

    assert load_script("dataset_report").main(["--input", str(cleaned), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    # The six fixture modules share their docstrings, so cleaning collapses the
    # near-duplicate tasks. That is the deduplicator doing its job.
    raw_records = [line for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(raw_records) == 36
    assert 0 < report["total_records"] < 36
    assert set(report["source_counts"]) <= {
        "local_code/implement",
        "local_code/explain",
        "local_code/document",
    }

    training_file = tmp_path / "sft.jsonl"
    assert (
        load_script("build_sft_dataset").main(
            [
                "--input",
                str(cleaned),
                "--output",
                str(training_file),
                "--eval-ratio",
                "0.2",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert training_file.exists()
    assert training_file.with_name("sft.eval.jsonl").exists()

    records = [json.loads(line) for line in training_file.read_text(encoding="utf-8").splitlines()]
    assert all("messages" in record for record in records)
    assert all(record["meta"]["license"] == "MIT" for record in records)


def test_secret_scanner_finds_a_planted_credential(tmp_path, capsys):
    leaky = tmp_path / "leaky"
    leaky.mkdir()
    (leaky / "config.py").write_text(
        'GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"\n', encoding="utf-8"
    )
    exit_code = load_script("scan_secrets").main(["--path", str(leaky)])
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "github_token" in output
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in output


def test_external_collectors_refuse_without_accepted_terms(capsys):
    for script_name in (
        "collect_codesearchnet",
        "collect_stack_sample",
        "collect_fineweb_edu",
        "collect_openwebtext",
    ):
        assert load_script(script_name).main([]) == 2
        message = capsys.readouterr().err
        assert "--accept-terms" in message


def test_download_model_refuses_without_confirmation(capsys):
    exit_code = load_script("download_model").main(["--model-id", "Qwen/Qwen2.5-Coder-7B-Instruct"])
    assert exit_code == 2
    assert "--accept-download" in capsys.readouterr().err


def test_training_script_reports_a_missing_dataset(tmp_path):
    with pytest.raises(SystemExit) as raised:
        load_script("train_qlora").main(
            [
                "--config",
                "configs/training/qlora_7b.yaml",
                "--dataset",
                str(tmp_path / "absent.jsonl"),
                "--dry-run",
            ]
        )
    assert "no dataset" in str(raised.value)
