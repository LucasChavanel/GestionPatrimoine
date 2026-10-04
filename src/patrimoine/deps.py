from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from .db import get_session
from .models.property import Property

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_property_or_404(property_id: int, session: Session = Depends(get_session)) -> Property:
    """Chaque bien a sa propre URL (/biens/{property_id}/...) — le bien actif est
    toujours explicite, jamais un état caché, pour ne jamais saisir une donnée
    sur le mauvais bien par inadvertance."""
    property_ = session.get(Property, property_id)
    if property_ is None:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    return property_
