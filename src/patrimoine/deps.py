from datetime import date
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .db import get_engine, get_session
from .fiscal.loader import load_fiscal_params
from .models.property import Property

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _avertissements_globaux(request: Request) -> dict:
    """Injecté dans le contexte de chaque template (voir context_processors
    ci-dessous) — affiché via la pastille cliquable de la nav latérale
    (base.html), jamais calculé par chaque route individuellement."""
    annee = date.today().year
    avertissements = list(load_fiscal_params(annee).unverified_warnings())
    with Session(get_engine()) as session:
        properties = session.exec(select(Property)).all()
        for property_ in properties:
            if not property_.numero_declaration_mairie:
                avertissements.append(f"{property_.nom} : numéro de déclaration en mairie non renseigné.")
    return {"avertissements_globaux": avertissements}


templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_avertissements_globaux])


def get_property_or_404(property_id: int, session: Session = Depends(get_session)) -> Property:
    """Chaque bien a sa propre URL (/biens/{property_id}/...) — le bien actif est
    toujours explicite, jamais un état caché, pour ne jamais saisir une donnée
    sur le mauvais bien par inadvertance."""
    property_ = session.get(Property, property_id)
    if property_ is None:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    return property_
