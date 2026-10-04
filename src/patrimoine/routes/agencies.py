from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.agency import Agency

router = APIRouter(prefix="/agences")


@router.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    agencies = session.exec(select(Agency).order_by(Agency.nom)).all()
    return templates.TemplateResponse(
        request, "agencies/liste.html", {"agencies": agencies, "agency_edit": None}
    )


@router.get("/{agency_id}/modifier")
def modifier_formulaire(agency_id: int, request: Request, session: Session = Depends(get_session)):
    agencies = session.exec(select(Agency).order_by(Agency.nom)).all()
    agency_edit = session.get(Agency, agency_id)
    return templates.TemplateResponse(
        request, "agencies/liste.html", {"agencies": agencies, "agency_edit": agency_edit}
    )


@router.post("")
def creer(
    session: Session = Depends(get_session),
    nom: str = Form(...),
    commission_pct_defaut: float = Form(...),
    notes: str | None = Form(None),
):
    agency = Agency(nom=nom, commission_pct_defaut=commission_pct_defaut, notes=notes or None)
    session.add(agency)
    session.commit()
    return RedirectResponse(url="/agences", status_code=303)


@router.post("/{agency_id}")
def modifier(
    agency_id: int,
    session: Session = Depends(get_session),
    nom: str = Form(...),
    commission_pct_defaut: float = Form(...),
    notes: str | None = Form(None),
):
    agency = session.get(Agency, agency_id)
    if agency is None:
        return RedirectResponse(url="/agences", status_code=303)
    agency.nom = nom
    agency.commission_pct_defaut = commission_pct_defaut
    agency.notes = notes or None
    session.add(agency)
    session.commit()
    return RedirectResponse(url="/agences", status_code=303)


@router.post("/{agency_id}/supprimer")
def supprimer(agency_id: int, session: Session = Depends(get_session)):
    agency = session.get(Agency, agency_id)
    if agency is not None:
        session.delete(agency)
        session.commit()
    return RedirectResponse(url="/agences", status_code=303)
