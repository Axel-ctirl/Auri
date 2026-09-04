"""The corpus and pipeline that make a set of weights answer as Bread.

These tests guard two things: that the pipeline produces well-formed training
data, and that the corpus keeps its promises about what Bread will claim to be.
The second matters more. A single careless answer in prompts/identity.yaml
teaches the model to repeat it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
CORPUS_PATH = REPO_ROOT / "prompts" / "identity.yaml"


def load_script(name: str):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"bread_script_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def corpus() -> dict:
    return yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))


def all_answers(corpus: dict) -> list[str]:
    answers = [group["answer"] for group in corpus["identity"]]
    for section in ("style_examples", "uncertainty_examples", "domain_examples"):
        answers.extend(example["assistant"] for example in corpus.get(section, []))
    return answers


# ------------------------------------------------------------------- corpus
def test_corpus_is_well_formed(corpus):
    assert corpus["name"] == "Bread"
    assert corpus["base_model"]
    assert corpus["base_license"]

    for group in corpus["identity"]:
        assert group["questions"], "an identity group has no phrasings"
        assert group["answer"].strip(), "an identity group has no answer"
        assert all(question.strip() for question in group["questions"])

    for section in ("style_examples", "uncertainty_examples", "domain_examples"):
        for example in corpus[section]:
            assert example["user"].strip()
            assert example["assistant"].strip()


def test_identity_questions_are_unique(corpus):
    questions = [
        question.lower().strip() for group in corpus["identity"] for question in group["questions"]
    ]
    duplicates = {question for question in questions if questions.count(question) > 1}
    assert not duplicates, f"the same question is answered twice: {duplicates}"


def test_corpus_never_claims_to_be_a_frontier_model(corpus):
    """The whole point of the corpus is that it does not teach this."""

    forbidden = [
        r"\bI am Claude\b",
        r"\bI am ChatGPT\b",
        r"\bI am GPT-\d",
        r"\bmade by Anthropic\b(?!\s*(?:or|,))",
        r"\bas (?:good|capable) as (?:Claude|GPT|ChatGPT)\b",
        r"\btrained from scratch\b(?!\.)",
        r"\bI was pretrained\b",
        r"\bbetter than (?:Claude|GPT|ChatGPT)\b",
    ]
    for answer in all_answers(corpus):
        for pattern in forbidden:
            match = re.search(pattern, answer, re.IGNORECASE)
            assert match is None, f"corpus claims '{match.group(0)}' in:\n{answer[:200]}"


def test_corpus_states_what_bread_is_derived_from(corpus):
    joined = "\n".join(group["answer"] for group in corpus["identity"])
    assert "{base_model}" in joined, "no answer names the base model"
    assert "{base_license}" in joined, "no answer names the base license"
    assert "fine-tune" in joined.lower()


def test_corpus_answers_the_questions_users_actually_ask(corpus):
    questions = " ".join(
        question.lower() for group in corpus["identity"] for question in group["questions"]
    )
    for expected in ("who are you", "are you claude", "are you chatgpt", "what model are you"):
        assert expected in questions, f"the corpus never answers '{expected}'"


# ------------------------------------------------------------------ builder
def test_builder_produces_valid_training_records(tmp_path, capsys):
    from app.services.datasets.records import read_jsonl, validate_record

    output = tmp_path / "identity.jsonl"
    exit_code = load_script("build_identity_dataset").main(
        ["--output", str(output), "--repeat", "1", "--eval-ratio", "0"]
    )
    capsys.readouterr()
    assert exit_code == 0

    records = [record for _n, record, error in read_jsonl(output) if record and not error]
    assert len(records) > 50

    for record in records:
        assert validate_record(record, "sft_chat") == []
        assert record["messages"][0]["role"] == "system"
        assert "You are Bread" in record["messages"][0]["content"]
        assert record["meta"]["source"].startswith("bread_identity/")


def test_placeholders_are_substituted_and_code_braces_survive(tmp_path, capsys):
    from app.services.datasets.records import read_jsonl, record_text

    output = tmp_path / "identity.jsonl"
    load_script("build_identity_dataset").main(
        ["--output", str(output), "--repeat", "1", "--eval-ratio", "0"]
    )
    capsys.readouterr()

    text = "\n".join(
        record_text(record) for _n, record, error in read_jsonl(output) if record and not error
    )
    assert "{base_model}" not in text
    assert "{base_license}" not in text
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in text
    # The corpus is full of literal braces in code samples; str.format would
    # have raised or mangled them.
    assert "${{ github.ref }}" in text
    assert 'f"Total: {total_sales(rows):,}"' in text


def test_base_model_override_keeps_the_answers_truthful(tmp_path, capsys):
    from app.services.datasets.records import read_jsonl, record_text

    output = tmp_path / "identity.jsonl"
    load_script("build_identity_dataset").main(
        [
            "--output",
            str(output),
            "--repeat",
            "1",
            "--eval-ratio",
            "0",
            "--base-model",
            "some-org/some-other-coder-3b",
        ]
    )
    capsys.readouterr()

    text = "\n".join(
        record_text(record) for _n, record, error in read_jsonl(output) if record and not error
    )
    assert "some-org/some-other-coder-3b" in text
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" not in text


def test_builder_warns_when_no_general_data_is_mixed_in(tmp_path, capsys):
    output = tmp_path / "identity.jsonl"
    load_script("build_identity_dataset").main(["--output", str(output), "--repeat", "1"])
    printed = capsys.readouterr().out
    assert "forget how to code" in printed


def test_mixing_general_data_lowers_the_identity_share(tmp_path, capsys):
    from app.services.datasets.records import RecordMeta, make_chat_record, read_jsonl, write_jsonl

    general = tmp_path / "general.jsonl"
    write_jsonl(
        general,
        [
            make_chat_record(
                system=None,
                user=f"Explain function number {index} in this module.",
                assistant=f"It returns element {index} of the sequence.",
                meta=RecordMeta(source="local_code", license="MIT", language="python"),
            )
            for index in range(600)
        ],
    )

    output = tmp_path / "identity.jsonl"
    load_script("build_identity_dataset").main(
        [
            "--output",
            str(output),
            "--repeat",
            "1",
            "--eval-ratio",
            "0",
            "--mix",
            str(general),
            "--mix-ratio",
            "4",
        ]
    )
    printed = capsys.readouterr().out
    assert "forget how to code" not in printed

    sources = [
        record["meta"]["source"] for _n, record, error in read_jsonl(output) if record and not error
    ]
    identity = [source for source in sources if source.startswith("bread_identity/")]
    assert 0 < len(identity) / len(sources) < 0.30


def test_missing_mix_file_is_a_clean_failure(tmp_path, capsys):
    exit_code = load_script("build_identity_dataset").main(
        ["--output", str(tmp_path / "out.jsonl"), "--mix", str(tmp_path / "absent.jsonl")]
    )
    capsys.readouterr()
    assert exit_code == 1


# --------------------------------------------------------------- model card
def test_model_card_states_what_the_weights_are_not(tmp_path):
    bake = load_script("bake_bread_model")
    merged_dir = tmp_path / "bread-coder-7b"

    card_path = bake.write_model_card(
        merged_dir,
        {
            "base_model_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_target_modules": ["q_proj", "v_proj"],
            "learning_rate": 0.0001,
            "num_train_epochs": 2,
            "max_seq_length": 2048,
        },
        {"model_name": "bread-coder-7b"},
        {
            "base_license": "Apache-2.0",
            "record_count": 4200,
            "identity_share": "3.2%",
            "baked_at": "2026-09-03T00:00:00+00:00",
        },
    )

    card = card_path.read_text(encoding="utf-8")
    assert "It was not trained from scratch" in card
    assert "not equal to a hosted frontier model" in card
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in card
    assert "Apache-2.0" in card
    assert "It writes code; it does not run code." in card
    # The YAML front matter is what Hugging Face reads for attribution.
    assert card.startswith("---\nbase_model: Qwen/Qwen2.5-Coder-7B-Instruct")


def test_provenance_file_records_that_this_is_a_derivative(tmp_path):
    bake = load_script("bake_bread_model")
    merged_dir = tmp_path / "weights"
    merged_dir.mkdir()

    path = bake.write_provenance(
        merged_dir,
        {"name": "bread-coder-7b", "base_model": "Qwen/x", "trained_from_scratch": False},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["trained_from_scratch"] is False
    assert payload["base_model"] == "Qwen/x"


def test_parameter_hint_reads_the_size_out_of_the_model_id():
    bake = load_script("bake_bread_model")
    assert bake.parameter_hint("Qwen/Qwen2.5-Coder-7B-Instruct") == "7B-parameter"
    assert bake.parameter_hint("org/mystery-model") == "small"


# --------------------------------------------------------------------- bake
def test_bake_config_points_at_the_identity_corpus():
    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "training" / "bread_identity.yaml").read_text(encoding="utf-8")
    )
    assert config["method"] == "qlora"
    assert config["bake"]["model_name"]
    assert config["bake"]["merged_dir"].startswith("data/models/")
    # A lower learning rate than the general config, on purpose.
    general = yaml.safe_load(
        (REPO_ROOT / "configs" / "training" / "qlora_7b.yaml").read_text(encoding="utf-8")
    )
    assert config["learning_rate"] < general["learning_rate"]


def test_bake_dry_run_writes_no_weights(tmp_path, capsys):
    bake = load_script("bake_bread_model")
    exit_code = bake.main(["--dry-run", "--output-name", "test-bake"])
    printed = capsys.readouterr().out
    assert exit_code in {0, 2}  # 2 when torch is absent, which is a clean stop.
    assert "Step 1/4" in printed
    assert not (REPO_ROOT / "data" / "models" / "test-bake").exists()
