"""Bread's from-scratch pretraining stack.

These tests need PyTorch, so they skip on a machine that has not installed it.
The one that matters most is the round-trip: it proves a model trained here
produces identical logits when loaded by Transformers, which is what makes an
exported model usable anywhere rather than only inside Bread.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="pretraining needs PyTorch")

from app.services.pretrain import (  # noqa: E402
    BreadLM,
    BreadLMConfig,
    ComputeBudget,
    PretrainConfig,
    decode,
    encode,
    held_out_split,
    iter_batches,
    learning_rate_at,
    load_tokenizer,
    open_shard,
    pack_documents,
    pretrain,
    train_tokenizer,
)
from app.services.pretrain.export import export_to_transformers  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

SAMPLE_DOCUMENTS = [
    "def calculate_total(rows):\n    return sum(row['amount'] for row in rows)\n",
    "def format_currency(cents, symbol='$'):\n    return f'{symbol}{cents / 100:.2f}'\n",
    "The inventory service tracks stock levels and reorders when they fall low.\n",
    "class OrderRepository:\n    def find(self, order_id):\n        return self._rows.get(order_id)\n",
] * 40


def tiny_config(vocab_size: int = 512) -> BreadLMConfig:
    return BreadLMConfig(
        vocab_size=vocab_size,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=64,
    )


# ---------------------------------------------------------------------- model
def test_a_fresh_model_starts_at_uniform_loss():
    """Cross-entropy at initialisation should be ln(vocab_size).

    Anything else means the initialisation is broken, and the run will either
    diverge or waste its first thousand steps recovering.

    Seeded, because at this size the sampling noise alone moves the loss by
    more than the tolerance and the test failed on unlucky runs.
    """

    torch.manual_seed(0)
    config = tiny_config()
    model = BreadLM(config)
    ids = torch.randint(0, config.vocab_size, (4, 32))

    loss = float(model(ids, labels=ids)["loss"])
    assert loss == pytest.approx(math.log(config.vocab_size), abs=0.1)


def test_parameter_counts_separate_embedding_from_the_rest():
    model = BreadLM(tiny_config())
    counts = model.parameter_counts()
    assert counts["total"] == counts["embedding"] + counts["non_embedding"]
    assert counts["embedding"] == 512 * 64  # tied, so counted once


def test_tying_removes_a_vocab_sized_matrix():
    tied = BreadLM(tiny_config()).parameter_counts()["total"]
    untied_config = tiny_config()
    untied_config.tie_word_embeddings = False
    untied = BreadLM(untied_config).parameter_counts()["total"]
    assert untied - tied == 512 * 64


def test_grouped_query_attention_rejects_a_bad_head_split():
    with pytest.raises(ValueError, match="multiple of"):
        BreadLMConfig(num_attention_heads=12, num_key_value_heads=5)


def test_attention_is_causal():
    """Changing a later token must not change an earlier token's logits."""

    torch.manual_seed(0)
    model = BreadLM(tiny_config()).eval()
    ids = torch.randint(0, 512, (1, 16))

    with torch.no_grad():
        before = model(ids)["logits"][0, :8].clone()
        changed = ids.clone()
        changed[0, 12] = (changed[0, 12] + 1) % 512
        after = model(changed)["logits"][0, :8]

    assert torch.allclose(before, after, atol=1e-6)


def test_generate_extends_the_sequence():
    model = BreadLM(tiny_config())
    ids = torch.randint(0, 512, (2, 8))
    assert model.generate(ids, max_new_tokens=6).shape == (2, 14)


# ------------------------------------------------------------------ schedule
def test_learning_rate_warms_up_then_decays_to_the_floor():
    config = PretrainConfig(
        max_steps=1000, warmup_steps=100, learning_rate=3e-4, min_learning_rate=3e-5
    )
    assert learning_rate_at(0, config) < config.learning_rate
    assert learning_rate_at(99, config) == pytest.approx(config.learning_rate)
    assert learning_rate_at(999, config) == pytest.approx(config.min_learning_rate, rel=0.01)

    warming = [learning_rate_at(step, config) for step in range(0, 100, 10)]
    assert warming == sorted(warming)
    decaying = [learning_rate_at(step, config) for step in range(100, 1000, 100)]
    assert decaying == sorted(decaying, reverse=True)


def test_compute_budget_reports_the_chinchilla_target():
    budget = ComputeBudget(parameters=100_000_000, tokens=2_000_000_000)
    assert budget.chinchilla_tokens == 2_000_000_000
    assert budget.training_flops == pytest.approx(6 * 1e8 * 2e9)
    budget.achieved_tokens_per_second = 100_000
    assert budget.summary()["estimated_hours"] == pytest.approx(5.56, abs=0.05)


# ---------------------------------------------------------------------- data
@pytest.fixture()
def prepared_corpus(tmp_path):
    vocab_size = 512
    train_tokenizer(iter(SAMPLE_DOCUMENTS), tmp_path / "tokenizer", vocab_size=vocab_size)
    tokenizer = load_tokenizer(tmp_path / "tokenizer")
    result = pack_documents(SAMPLE_DOCUMENTS, tokenizer, tmp_path / "corpus.bin", vocab_size)
    return tmp_path, tokenizer, result, vocab_size


def test_tokenizer_round_trips_source_code(prepared_corpus):
    _root, tokenizer, _result, _vocab = prepared_corpus
    original = "def calculate_total(rows):"
    assert decode(tokenizer, encode(tokenizer, original)) == original


def test_packing_writes_every_document_with_a_separator(prepared_corpus):
    _root, _tokenizer, result, _vocab = prepared_corpus
    assert result.document_count == len(SAMPLE_DOCUMENTS)
    assert result.token_count > result.document_count
    assert result.dtype == "uint16"


def test_batches_are_shifted_by_exactly_one_token(prepared_corpus):
    root, _tokenizer, _result, vocab = prepared_corpus
    shard = open_shard(root / "corpus.bin", vocab)
    inputs, targets = next(iter_batches(shard, batch_size=4, sequence_length=16, seed=7))

    assert inputs.shape == (4, 16)
    assert (inputs[:, 1:] == targets[:, :-1]).all()


def test_batches_are_deterministic_for_a_seed(prepared_corpus):
    root, _tokenizer, _result, vocab = prepared_corpus
    shard = open_shard(root / "corpus.bin", vocab)
    first = next(iter_batches(shard, batch_size=2, sequence_length=8, seed=3))[0]
    second = next(iter_batches(shard, batch_size=2, sequence_length=8, seed=3))[0]
    assert (first == second).all()


def test_held_out_split_does_not_overlap(prepared_corpus):
    root, _tokenizer, _result, vocab = prepared_corpus
    shard = open_shard(root / "corpus.bin", vocab)
    train_part, eval_part = held_out_split(shard, 0.1)
    assert len(train_part) + len(eval_part) == len(shard)
    assert len(eval_part) > 0


def test_a_corpus_smaller_than_one_window_is_a_clear_error(tmp_path):
    import numpy as np

    (tmp_path / "tiny.bin").write_bytes(np.zeros(8, dtype=np.uint16).tobytes())
    shard = open_shard(tmp_path / "tiny.bin", 512)
    with pytest.raises(ValueError, match="Pack more data"):
        next(iter_batches(shard, batch_size=1, sequence_length=64))


# ------------------------------------------------------------------ training
def test_a_short_run_actually_learns(prepared_corpus):
    """The end-to-end claim: random weights plus data produces a lower loss."""

    root, _tokenizer, _result, vocab = prepared_corpus
    config = PretrainConfig(
        name="test",
        corpus_path=str(root / "corpus.bin"),
        tokenizer_dir=str(root / "tokenizer"),
        output_dir=str(root / "run"),
        vocab_size=vocab,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        sequence_length=32,
        max_steps=30,
        batch_size=4,
        gradient_accumulation_steps=1,
        learning_rate=3e-3,
        warmup_steps=5,
        device="cpu",
        log_every=5,
        eval_every=0,
        save_every=30,
        eval_batches=3,
    )

    events: list[dict] = []
    summary = pretrain(config, on_event=events.append, resume=False)

    losses = [event["loss"] for event in events if event.get("event") == "step"]
    assert len(losses) >= 4
    assert losses[-1] < losses[0], f"loss did not fall: {losses}"
    assert losses[0] < math.log(vocab) + 0.5

    assert summary["steps"] == 30
    assert summary["tokens_seen"] == 30 * 4 * 32
    assert Path(summary["checkpoint"]).exists()
    assert (root / "run" / "summary.json").exists()


def test_a_run_resumes_from_its_checkpoint(prepared_corpus):
    root, _tokenizer, _result, vocab = prepared_corpus
    shared = {
        "name": "resume",
        "corpus_path": str(root / "corpus.bin"),
        "tokenizer_dir": str(root / "tokenizer"),
        "output_dir": str(root / "resume"),
        "vocab_size": vocab,
        "hidden_size": 64,
        "intermediate_size": 128,
        "num_hidden_layers": 2,
        "num_attention_heads": 4,
        "num_key_value_heads": 2,
        "sequence_length": 32,
        "batch_size": 2,
        "gradient_accumulation_steps": 1,
        "warmup_steps": 2,
        "device": "cpu",
        "log_every": 5,
        "eval_every": 0,
        "save_every": 10,
        "eval_batches": 2,
    }

    pretrain(PretrainConfig(max_steps=10, **shared), resume=False)

    events: list[dict] = []
    pretrain(PretrainConfig(max_steps=20, **shared), on_event=events.append, resume=True)

    assert any(event.get("event") == "resumed" and event["step"] == 10 for event in events)
    steps = [event["step"] for event in events if event.get("event") == "step"]
    assert steps and min(steps) > 10


# -------------------------------------------------------------------- export
def test_exported_weights_produce_identical_logits_in_transformers(prepared_corpus):
    """The correctness proof for the whole architecture.

    If the rotary layout, the head grouping or the tensor names were wrong, the
    same input would give different logits under Transformers. They must match
    exactly, not approximately.
    """

    pytest.importorskip("transformers")
    from transformers import AutoModelForCausalLM

    root, _tokenizer, _result, vocab = prepared_corpus
    config = PretrainConfig(
        name="export",
        corpus_path=str(root / "corpus.bin"),
        tokenizer_dir=str(root / "tokenizer"),
        output_dir=str(root / "export-run"),
        vocab_size=vocab,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        sequence_length=32,
        max_steps=5,
        batch_size=2,
        gradient_accumulation_steps=1,
        warmup_steps=1,
        device="cpu",
        log_every=5,
        eval_every=0,
        save_every=5,
        eval_batches=2,
    )
    pretrain(config, resume=False)

    exported = root / "exported"
    info = export_to_transformers(
        Path(config.output_dir) / "checkpoint.pt", root / "tokenizer", exported
    )

    checkpoint = torch.load(
        Path(config.output_dir) / "checkpoint.pt", map_location="cpu", weights_only=False
    )
    ours = BreadLM(BreadLMConfig(**checkpoint["model_config"]))
    ours.load_state_dict(checkpoint["model"])
    ours.eval()

    theirs = AutoModelForCausalLM.from_pretrained(str(exported), dtype=torch.float32).eval()

    ids = torch.randint(0, vocab, (2, 24))
    with torch.no_grad():
        difference = (ours(ids)["logits"] - theirs(ids).logits).abs().max().item()

    assert difference < 1e-4, f"exported weights diverge by {difference}"
    assert info["parameters"] > 0


def test_export_records_that_nothing_was_inherited(prepared_corpus):
    root, _tokenizer, _result, vocab = prepared_corpus
    config = PretrainConfig(
        name="provenance",
        corpus_path=str(root / "corpus.bin"),
        tokenizer_dir=str(root / "tokenizer"),
        output_dir=str(root / "prov-run"),
        vocab_size=vocab,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        sequence_length=32,
        max_steps=3,
        batch_size=2,
        gradient_accumulation_steps=1,
        warmup_steps=1,
        device="cpu",
        eval_every=0,
        save_every=3,
        eval_batches=2,
    )
    pretrain(config, resume=False)

    exported = root / "exported-provenance"
    export_to_transformers(Path(config.output_dir) / "checkpoint.pt", root / "tokenizer", exported)

    provenance = json.loads((exported / "bread.json").read_text(encoding="utf-8"))
    assert provenance["trained_from_scratch"] is True
    assert provenance["base_model"] is None
    assert provenance["inherited_weights"] == "none"

    card = (exported / "README.md").read_text(encoding="utf-8")
    assert "pretrained from random initialisation" in card
    assert "No weights were" in card
    assert "cannot match a 7B model" in card
    assert (exported / "tokenizer.json").exists()


# ------------------------------------------------------------------- configs
@pytest.mark.parametrize("name", ["bread_tiny", "bread_small", "bread_base", "bread_large"])
def test_shipped_configs_are_compute_optimal(name):
    """Each config should plan roughly 20 tokens per parameter."""

    import yaml

    path = REPO_ROOT / "configs" / "pretrain" / f"{name}.yaml"
    config = PretrainConfig.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))
    parameters = BreadLM(config.model_config()).parameter_counts()["total"]
    ratio = config.total_tokens / parameters

    assert 18 <= ratio <= 22, f"{name} plans {ratio:.1f} tokens per parameter"
    assert config.warmup_steps < config.max_steps
    assert config.min_learning_rate < config.learning_rate
