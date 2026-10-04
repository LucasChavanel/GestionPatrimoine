from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..fiscal.loader import load_fiscal_params
from ..models.enums import EntityType, NatureWorks
from ..models.furniture import Furniture
from ..models.property import Property
from ..models.works import Works
from ..services.amortization import dotation_furniture, dotation_works, is_furniture_charge_directe
from ..services.attachments import list_attachments

router = APIRouter(prefix="/biens/{property_id}/travaux")


def _context(session: Session, property_: Property, annee: int):
    works_list = session.exec(
        select(Works).where(Works.property_id == property_.id).order_by(Works.date)
    ).all()
    furniture_list = session.exec(
        select(Furniture).where(Furniture.property_id == property_.id).order_by(Furniture.date_achat)
    ).all()

    works_rows = [
        {
            "item": w,
            "dotation_annee": dotation_works(w, annee),
            "attachments": list_attachments(session, EntityType.works, w.id) if w.id else [],
        }
        for w in works_list
    ]

    furniture_rows = []
    for f in furniture_list:
        params_achat = load_fiscal_params(f.date_achat.year)
        furniture_rows.append(
            {
                "item": f,
                "charge_directe": is_furniture_charge_directe(f, params_achat),
                "dotation_annee": dotation_furniture(f, annee, params_achat),
                "attachments": list_attachments(session, EntityType.furniture, f.id) if f.id else [],
            }
        )

    fiscal_params = load_fiscal_params(date.today().year)

    return {
        "property_": property_,
        "works_rows": works_rows,
        "furniture_rows": furniture_rows,
        "annee": annee,
        "natures_works": list(NatureWorks),
        "duree_suggeree_agencements": fiscal_params.meuble_tourisme.amortissement.durees_defaut.agencements,
        "duree_suggeree_mobilier": fiscal_params.meuble_tourisme.amortissement.durees_defaut.mobilier,
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
    return templates.TemplateResponse(request, "property/travaux.html", _context(session, property_, annee))


@router.post("/works")
def creer_works(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: str | None = Form(None),
    description: str | None = Form(None),
    nature: NatureWorks = Form(...),
    duree_amortissement: str | None = Form(None),
    avant_premiere_mise_en_location: str | None = Form(None),
):
    works = Works(
        property_id=property_id,
        date=date.fromisoformat(date_),
        montant_ttc=montant_ttc,
        fournisseur=fournisseur or None,
        description=description or None,
        nature=nature,
        duree_amortissement=int(duree_amortissement) if duree_amortissement else None,
        avant_premiere_mise_en_location=bool(avant_premiere_mise_en_location),
    )
    session.add(works)
    session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/travaux?annee={works.date.year}", status_code=303)


@router.post("/works/{works_id}/supprimer")
def supprimer_works(
    property_id: int,
    works_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    works = session.get(Works, works_id)
    annee = works.date.year if works else date.today().year
    if works is not None:
        session.delete(works)
        session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/travaux?annee={annee}", status_code=303)


@router.post("/furniture")
def creer_furniture(
    property_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
    date_achat: str = Form(...),
    montant_ttc: float = Form(...),
    description: str | None = Form(None),
    duree_amortissement: int = Form(...),
):
    furniture = Furniture(
        property_id=property_id,
        date_achat=date.fromisoformat(date_achat),
        montant_ttc=montant_ttc,
        description=description or None,
        duree_amortissement=duree_amortissement,
    )
    session.add(furniture)
    session.commit()
    return RedirectResponse(
        url=f"/biens/{property_id}/travaux?annee={furniture.date_achat.year}", status_code=303
    )


@router.post("/furniture/{furniture_id}/supprimer")
def supprimer_furniture(
    property_id: int,
    furniture_id: int,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    furniture = session.get(Furniture, furniture_id)
    annee = furniture.date_achat.year if furniture else date.today().year
    if furniture is not None:
        session.delete(furniture)
        session.commit()
    return RedirectResponse(url=f"/biens/{property_id}/travaux?annee={annee}", status_code=303)
