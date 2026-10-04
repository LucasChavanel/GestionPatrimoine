from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..fiscal.loader import load_fiscal_params
from ..models.enums import NatureComposant, StatutClassement, TypeLocation
from ..models.property import BuildingComponent, Property

router_liste = APIRouter(prefix="/biens")
router_fiche = APIRouter(prefix="/biens/{property_id}")


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _parse_optional_float(value: str | None) -> float | None:
    if not value:
        return None
    return float(value)


@router_liste.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    properties = session.exec(select(Property).order_by(Property.nom)).all()
    return templates.TemplateResponse(
        request, "property/liste.html", {"properties": properties, "types_location": list(TypeLocation)}
    )


@router_liste.post("")
def creer(
    session: Session = Depends(get_session),
    nom: str = Form(...),
    adresse: str = Form(...),
    surface: float = Form(...),
    date_acquisition: str = Form(...),
    prix_acquisition: float = Form(...),
    frais_notaire: float = Form(0.0),
    part_terrain_pct: float = Form(0.0),
    type_location: TypeLocation = Form(TypeLocation.meuble_tourisme_non_classe),
    quote_part: float = Form(1.0),
):
    property_ = Property(
        nom=nom,
        adresse=adresse,
        surface=surface,
        date_acquisition=date.fromisoformat(date_acquisition),
        prix_acquisition=prix_acquisition,
        frais_notaire=frais_notaire,
        part_terrain_pct=part_terrain_pct,
        type_location=type_location,
        quote_part=quote_part,
    )
    session.add(property_)
    session.commit()
    session.refresh(property_)
    return RedirectResponse(url=f"/biens/{property_.id}", status_code=303)


@router_fiche.get("")
def fiche(
    request: Request,
    property_: Property = Depends(get_property_or_404),
):
    fiscal_params = load_fiscal_params(date.today().year)
    return templates.TemplateResponse(
        request,
        "property/fiche.html",
        {
            "property_": property_,
            "natures_composant": list(NatureComposant),
            "types_location": list(TypeLocation),
            "durees_defaut": fiscal_params.meuble_tourisme.amortissement.durees_defaut,
        },
    )


@router_fiche.post("")
def enregistrer(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    nom: str = Form(...),
    adresse: str = Form(...),
    surface: float = Form(...),
    date_acquisition: str = Form(...),
    prix_acquisition: float = Form(...),
    frais_notaire: float = Form(0.0),
    part_terrain_pct: float = Form(0.0),
    type_location: TypeLocation = Form(TypeLocation.meuble_tourisme_non_classe),
    quote_part: float = Form(1.0),
    statut_classement: StatutClassement = Form(StatutClassement.non_classe),
    nb_etoiles: str | None = Form(None),
    date_classement: str | None = Form(None),
    numero_declaration_mairie: str | None = Form(None),
    date_premiere_mise_en_location: str | None = Form(None),
    valeur_estimee: str | None = Form(None),
    valeur_estimee_date: str | None = Form(None),
):
    property_.nom = nom
    property_.adresse = adresse
    property_.surface = surface
    property_.date_acquisition = date.fromisoformat(date_acquisition)
    property_.prix_acquisition = prix_acquisition
    property_.frais_notaire = frais_notaire
    property_.part_terrain_pct = part_terrain_pct
    property_.type_location = type_location
    property_.quote_part = quote_part
    property_.statut_classement = statut_classement
    property_.nb_etoiles = _parse_optional_int(nb_etoiles)
    property_.date_classement = _parse_optional_date(date_classement)
    property_.numero_declaration_mairie = numero_declaration_mairie or None
    property_.date_premiere_mise_en_location = _parse_optional_date(date_premiere_mise_en_location)
    property_.valeur_estimee = _parse_optional_float(valeur_estimee)
    property_.valeur_estimee_date = _parse_optional_date(valeur_estimee_date)

    session.add(property_)
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}", status_code=303)


@router_fiche.post("/composants")
def ajouter_composant(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    nature: NatureComposant = Form(...),
    part_du_prix_pct: float = Form(...),
    duree_amortissement: int = Form(...),
):
    composant = BuildingComponent(
        property_id=property_id,
        nature=nature,
        part_du_prix_pct=part_du_prix_pct,
        duree_amortissement=duree_amortissement,
    )
    session.add(composant)
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}", status_code=303)


@router_fiche.post("/composants/{composant_id}/supprimer")
def supprimer_composant(
    property_id: int,
    composant_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    composant = session.get(BuildingComponent, composant_id)
    if composant is not None:
        session.delete(composant)
        session.commit()
    return RedirectResponse(url=f"/biens/{property_id}", status_code=303)
