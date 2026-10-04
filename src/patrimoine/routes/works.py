from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_the_property, templates
from ..fiscal.loader import load_fiscal_params
from ..models.enums import EntityType, NatureWorks
from ..models.furniture import Furniture
from ..models.works import Works
from ..services.amortization import dotation_furniture, dotation_works, is_furniture_charge_directe
from ..services.attachments import list_attachments

router = APIRouter(prefix="/appartement/travaux")


def _context(session: Session, annee: int):
    property_ = get_the_property(session)
    works_list: list[Works] = []
    furniture_list: list[Furniture] = []
    if property_ is not None:
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
        "redirect_to": f"/appartement/travaux?annee={annee}",
    }


@router.get("")
def liste(request: Request, annee: Optional[int] = None, session: Session = Depends(get_session)):
    annee = annee or date.today().year
    return templates.TemplateResponse(request, "property/travaux.html", _context(session, annee))


@router.post("/works")
def creer_works(
    session: Session = Depends(get_session),
    date_: str = Form(..., alias="date"),
    montant_ttc: float = Form(...),
    fournisseur: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    nature: NatureWorks = Form(...),
    duree_amortissement: Optional[str] = Form(None),
    avant_premiere_mise_en_location: Optional[str] = Form(None),
):
    property_ = get_the_property(session)
    if property_ is None or property_.id is None:
        return RedirectResponse(url="/appartement", status_code=303)

    works = Works(
        property_id=property_.id,
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
    return RedirectResponse(url=f"/appartement/travaux?annee={works.date.year}", status_code=303)


@router.post("/works/{works_id}/supprimer")
def supprimer_works(works_id: int, session: Session = Depends(get_session)):
    works = session.get(Works, works_id)
    annee = works.date.year if works else date.today().year
    if works is not None:
        session.delete(works)
        session.commit()
    return RedirectResponse(url=f"/appartement/travaux?annee={annee}", status_code=303)


@router.post("/furniture")
def creer_furniture(
    session: Session = Depends(get_session),
    date_achat: str = Form(...),
    montant_ttc: float = Form(...),
    description: Optional[str] = Form(None),
    duree_amortissement: int = Form(...),
):
    property_ = get_the_property(session)
    if property_ is None or property_.id is None:
        return RedirectResponse(url="/appartement", status_code=303)

    furniture = Furniture(
        property_id=property_.id,
        date_achat=date.fromisoformat(date_achat),
        montant_ttc=montant_ttc,
        description=description or None,
        duree_amortissement=duree_amortissement,
    )
    session.add(furniture)
    session.commit()
    return RedirectResponse(url=f"/appartement/travaux?annee={furniture.date_achat.year}", status_code=303)


@router.post("/furniture/{furniture_id}/supprimer")
def supprimer_furniture(furniture_id: int, session: Session = Depends(get_session)):
    furniture = session.get(Furniture, furniture_id)
    annee = furniture.date_achat.year if furniture else date.today().year
    if furniture is not None:
        session.delete(furniture)
        session.commit()
    return RedirectResponse(url=f"/appartement/travaux?annee={annee}", status_code=303)
