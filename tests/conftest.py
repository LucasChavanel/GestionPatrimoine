from __future__ import annotations

import pytest


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path / "data"))
    from patrimoine import config

    config.get_data_dir.cache_clear()
    yield tmp_path / "data"


@pytest.fixture
def session(data_dir):
    from patrimoine import db

    db.dispose_engine()
    db.run_migrations()
    from sqlmodel import Session

    with Session(db.get_engine()) as s:
        yield s
    db.dispose_engine()


@pytest.fixture
def client(data_dir):
    from patrimoine import db

    db.dispose_engine()
    db.run_migrations()
    from fastapi.testclient import TestClient

    from patrimoine.main import app

    with TestClient(app) as c:
        yield c
    db.dispose_engine()
