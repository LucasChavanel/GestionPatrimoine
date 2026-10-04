from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.coownership import CoOwnershipYear
from ..models.enums import EntityType
from ..services.attachments import list_attachments

router = APIRouter(prefix="/indivision")


def _attachments_by_year(session: Session, years: list[CoOwnershipYear]) -> dict[int, list]:
    return {y.id: list_attachments(session, EntityType.coownership_year, y.id) for y in years if y.id is not None}


@router.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    years = session.exec(select(CoOwnershipYear).order_by(CoOwnershipYear.annee.desc())).all()
    return templates.TemplateResponse(
        request,
        "indivision/liste.html",
        {
            "years": years,
            "year_edit": None,
            "attachments_by_year": _attachments_by_year(session, years),
            "redirect_to": "/indivision",
        },
    )


@router.get("/{year_id}/modifier")
def modifier_formulaire(year_id: int, request: Request, session: Session = Depends(get_session)):
    years = session.exec(select(CoOwnershipYear).order_by(CoOwnershipYear.annee.desc())).all()
    year_edit = session.get(CoOwnershipYear, year_id)
    return templates.TemplateResponse(
        request,
        "indivision/liste.html",
        {
            "years": years,
            "year_edit": year_edit,
            "attachments_by_year": _attachments_by_year(session, years),
            "redirect_to": "/indivision",
        },
    )


def _form_to_year(
    year: CoOwnershipYear,
    annee: int,
    libelle: str,
    quote_part_pct: float,
    revenus_bruts: float,
    charges: float,
    montants_proratises: str | None,
    regime_declare: str | None,
    montants_a_reporter: str | None,
) -> None:
    year.annee = annee
    year.libelle = libelle
    year.quote_part_pct = quote_part_pct
    year.revenus_bruts = revenus_bruts
    year.charges = charges
    year.montants_proratises = bool(montants_proratises)
    year.regime_declare = regime_declare or None
    year.montants_a_reporter = montants_a_reporter or None


@router.post("")
def creer(
    session: Session = Depends(get_session),
    annee: int = Form(...),
    libelle: str = Form(...),
    quote_part_pct: float = Form(...),
    revenus_bruts: float = Form(...),
    charges: float = Form(...),
    montants_proratises: str | None = Form(None),
    regime_declare: str | None = Form(None),
    montants_a_reporter: str | None = Form(None),
):
    year = CoOwnershipYear(annee=annee, libelle=libelle, quote_part_pct=quote_part_pct,
                            revenus_bruts=revenus_bruts, charges=charges, montants_proratises=False)
    _form_to_year(
        year, annee, libelle, quote_part_pct, revenus_bruts, charges,
        montants_proratises, regime_declare, montants_a_reporter,
    )
    session.add(year)
    session.commit()
    return RedirectResponse(url="/indivision", status_code=303)


@router.post("/{year_id}")
def modifier(
    year_id: int,
    session: Session = Depends(get_session),
    annee: int = Form(...),
    libelle: str = Form(...),
    quote_part_pct: float = Form(...),
    revenus_bruts: float = Form(...),
    charges: float = Form(...),
    montants_proratises: str | None = Form(None),
    regime_declare: str | None = Form(None),
    montants_a_reporter: str | None = Form(None),
):
    year = session.get(CoOwnershipYear, year_id)
    if year is None:
        return RedirectResponse(url="/indivision", status_code=303)
    _form_to_year(
        year, annee, libelle, quote_part_pct, revenus_bruts, charges,
        montants_proratises, regime_declare, montants_a_reporter,
    )
    session.add(year)
    session.commit()
    return RedirectResponse(url="/indivision", status_code=303)


@router.post("/{year_id}/supprimer")
def supprimer(year_id: int, session: Session = Depends(get_session)):
    year = session.get(CoOwnershipYear, year_id)
    if year is not None:
        session.delete(year)
        session.commit()
    return RedirectResponse(url="/indivision", status_code=303)
