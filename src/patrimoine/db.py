from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic.config import Config
from sqlmodel import Session, create_engine

from alembic import command

from . import (
    config,
    models,  # noqa: F401  s'assure que toutes les tables sont enregistrées
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.get_database_url(), connect_args={"check_same_thread": False}
        )
    return _engine


def _alembic_config() -> Config:
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", config.get_database_url())
    return cfg


def run_migrations() -> None:
    """Exécuté au démarrage de l'app : jamais de commande alembic manuelle à taper."""
    command.upgrade(_alembic_config(), "head")


def dispose_engine() -> None:
    """Force la réouverture de connexions fraîches (après une restauration, le
    fichier .db sur disque a été remplacé)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
