"""Résolution des chemins de données. Rien ici n'est versionné dans le repo."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "patrimoine"


@lru_cache
def get_data_dir() -> Path:
    """Dossier de données, configurable via PATRIMOINE_DATA_DIR (tests, usage avancé)."""
    override = os.environ.get("PATRIMOINE_DATA_DIR")
    data_dir = Path(override).expanduser() if override else _default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "documents").mkdir(parents=True, exist_ok=True)
    return data_dir


def get_documents_dir() -> Path:
    return get_data_dir() / "documents"


def get_database_path() -> Path:
    return get_data_dir() / "patrimoine.db"


def get_database_url() -> str:
    return f"sqlite:///{get_database_path()}"
