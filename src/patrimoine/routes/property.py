from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..deps import get_the_property, templates
from ..fiscal.loader import load_fiscal_params
from ..models.enums import NatureComposant, StatutClassement
from ..models.property import BuildingComponent, Property

router = APIRouter(prefix="/appartement")


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


@router.get("")
def fiche(request: Request, session: Session = Depends(get_session)):
    property_ = get_the_property(session)
    fiscal_params = load_fiscal_params(date.today().year)
    return templates.TemplateResponse(
        request,
        "property/fiche.html",
        {
            "property_": property_,
            "natures_composant": list(NatureComposant),
            "durees_defaut": fiscal_params.meuble_tourisme.amortissement.durees_defaut,
        },
    )


@router.post("")
def enregistrer(
    request: Request,
    session: Session = Depends(get_session),
    nom: str = Form(...),
    adresse: str = Form(...),
    surface: float = Form(...),
    date_acquisition: str = Form(...),
    prix_acquisition: float = Form(...),
    frais_notaire: float = Form(0.0),
    part_terrain_pct: float = Form(0.0),
    statut_classement: StatutClassement = Form(StatutClassement.non_classe),
    nb_etoiles: str | None = Form(None),
    date_classement: str | None = Form(None),
    numero_declaration_mairie: str | None = Form(None),
    date_premiere_mise_en_location: str | None = Form(None),
):
    property_ = get_the_property(session)
    if property_ is None:
        property_ = Property(
            nom=nom,
            adresse=adresse,
            surface=surface,
            date_acquisition=date.fromisoformat(date_acquisition),
            prix_acquisition=prix_acquisition,
        )

    property_.nom = nom
    property_.adresse = adresse
    property_.surface = surface
    property_.date_acquisition = date.fromisoformat(date_acquisition)
    property_.prix_acquisition = prix_acquisition
    property_.frais_notaire = frais_notaire
    property_.part_terrain_pct = part_terrain_pct
    property_.statut_classement = statut_classement
    property_.nb_etoiles = _parse_optional_int(nb_etoiles)
    property_.date_classement = _parse_optional_date(date_classement)
    property_.numero_declaration_mairie = numero_declaration_mairie or None
    property_.date_premiere_mise_en_location = _parse_optional_date(date_premiere_mise_en_location)

    session.add(property_)
    session.commit()
    return RedirectResponse(url="/appartement", status_code=303)


@router.post("/composants")
def ajouter_composant(
    session: Session = Depends(get_session),
    nature: NatureComposant = Form(...),
    part_du_prix_pct: float = Form(...),
    duree_amortissement: int = Form(...),
):
    property_ = get_the_property(session)
    if property_ is None or property_.id is None:
        return RedirectResponse(url="/appartement", status_code=303)

    composant = BuildingComponent(
        property_id=property_.id,
        nature=nature,
        part_du_prix_pct=part_du_prix_pct,
        duree_amortissement=duree_amortissement,
    )
    session.add(composant)
    session.commit()
    return RedirectResponse(url="/appartement", status_code=303)


@router.post("/composants/{composant_id}/supprimer")
def supprimer_composant(composant_id: int, session: Session = Depends(get_session)):
    composant = session.get(BuildingComponent, composant_id)
    if composant is not None:
        session.delete(composant)
        session.commit()
    return RedirectResponse(url="/appartement", status_code=303)
