"""Shared pytest fixtures.

Every test runs against a throwaway SQLite file and the mock inference backend,
so the suite needs no GPU, no model weights and no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture()
def bread_env(tmp_path, monkeypatch):
    """Point Bread at a temporary data directory and the mock backend."""

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BREAD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BREAD_DATABASE_URL", f"sqlite:///{(data_dir / 'test.db').as_posix()}")
    monkeypatch.setenv("MODEL_BACKEND", "mock")
    monkeypatch.setenv("MOCK_DELAY_SECONDS", "0")
    monkeypatch.setenv("EMBEDDING_BACKEND", "hashing")
    monkeypatch.setenv("BREAD_REQUIRE_API_KEY", "false")
    monkeypatch.setenv("BREAD_HOST", "127.0.0.1")
    monkeypatch.setenv("BREAD_RATE_LIMIT_REQUESTS", "10000")
    monkeypatch.delenv("BREAD_CONFIG_FILE", raising=False)

    from app import config, db
    from app.services.inference import registry
    from app.services.rag import embeddings, store

    config.reset_settings_cache()
    db.reset_engine()
    store.reset_vector_store()
    embeddings.clear_embedder_cache()
    registry.unload()

    yield config.get_settings()

    registry.stop_all()
    registry.unload()
    db.reset_engine()
    store.reset_vector_store()
    embeddings.clear_embedder_cache()
    config.reset_settings_cache()


@pytest.fixture()
def client(bread_env):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def session(bread_env):
    from sqlmodel import Session

    from app.db import get_engine, init_db

    init_db(bread_env)
    with Session(get_engine(bread_env)) as db_session:
        yield db_session
