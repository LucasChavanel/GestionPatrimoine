from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .models.property import Property

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_the_property(session: Session) -> Property | None:
    """Phase 1 : un seul bien géré par l'UI (le modèle supporte plusieurs biens via
    la FK property_id, mais aucun écran n'en gère plusieurs pour l'instant)."""
    return session.exec(select(Property)).first()
