from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..models.enums import EntityType, NatureImmobilisation
from ..models.immobilisation import Immobilisation
from ..models.property import Property
from ..services.amortization import dotation_immobilisation
from ..services.attachments import list_attachments

router = APIRouter(prefix="/biens/{property_id}/travaux")


def _context(session: Session, property_: Property, annee: int, immobilisation_edit: Immobilisation | None):
    immobilisations = session.exec(
        select(Immobilisation)
        .where(Immobilisation.property_id == property_.id)
        .order_by(Immobilisation.date_mise_en_service)
    ).all()

    rows = [
        {
            "item": i,
            "dotation_annee": dotation_immobilisation(i, annee),
            "attachments": list_attachments(session, EntityType.immobilisation, i.id) if i.id else [],
        }
        for i in immobilisations
    ]

    return {
        "property_": property_,
        "rows": rows,
        "annee": annee,
        "natures_immobilisation": list(NatureImmobilisation),
        "immobilisation_edit": immobilisation_edit,
        "redirect_to": f"/biens/{property_.id}/travaux?annee={annee}",
    }


@router.get("")
def liste(
    property_id: int,
    request: Request,
    annee: int | None = None,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    annee = annee or date.today().year
    return templates.TemplateResponse(
        request, "property/travaux.html", _context(session, property_, annee, None)
    )


@router.get("/{immobilisation_id}/modifier")
def modifier_formulaire(
    property_id: int,
    immobilisation_id: int,
    request: Request,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    immobilisation_edit = session.get(Immobilisation, immobilisation_id)
    annee = immobilisation_edit.date_mise_en_service.year if immobilisation_edit else date.today().year
    return templates.TemplateResponse(
        request, "property/travaux.html", _context(session, property_, annee, immobilisation_edit)
    )


@router.post("")
def creer(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    type_immo: NatureImmobilisation = Form(...),
    date_mise_en_service: str = Form(...),
    montant: float = Form(...),
    duree_ans: int = Form(...),
    avant_premiere_mise_en_location: str | None = Form(None),
    description: str | None = Form(None),
    fournisseur: str | None = Form(None),
):
    immo = Immobilisation(
        property_id=property_id,
        type=type_immo,
        date_mise_en_service=date.fromisoformat(date_mise_en_service),
        montant=montant,
        duree_ans=duree_ans,
        avant_premiere_mise_en_location=bool(avant_premiere_mise_en_location),
        description=description or None,
        fournisseur=fournisseur or None,
    )
    session.add(immo)
    session.commit()
    return RedirectResponse(
        url=f"/biens/{property_id}/travaux?annee={immo.date_mise_en_service.year}", status_code=303
    )


@router.post("/{immobilisation_id}")
def modifier(
    property_id: int,
    immobilisation_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    type_immo: NatureImmobilisation = Form(...),
    date_mise_en_service: str = Form(...),
    montant: float = Form(...),
    duree_ans: int = Form(...),
    avant_premiere_mise_en_location: str | None = Form(None),
    description: str | None = Form(None),
    fournisseur: str | None = Form(None),
):
    immo = session.get(Immobilisation, immobilisation_id)
    if immo is None:
        return RedirectResponse(url=f"/biens/{property_id}/travaux", status_code=303)
    immo.type = type_immo
    immo.date_mise_en_service = date.fromisoformat(date_mise_en_service)
    immo.montant = montant
    immo.duree_ans = duree_ans
    immo.avant_premiere_mise_en_location = bool(avant_premiere_mise_en_location)
    immo.description = description or None
    immo.fournisseur = fournisseur or None
    session.add(immo)
    session.commit()
    return RedirectResponse(
        url=f"/biens/{property_id}/travaux?annee={immo.date_mise_en_service.year}", status_code=303
    )


@router.post("/{immobilisation_id}/supprimer")
def supprimer(
    property_id: int,
    immobilisation_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    immo = session.get(Immobilisation, immobilisation_id)
    annee = immo.date_mise_en_service.year if immo else date.today().year
    if immo is not None:
        session.delete(immo)
        session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/travaux?annee={annee}", status_code=303)
