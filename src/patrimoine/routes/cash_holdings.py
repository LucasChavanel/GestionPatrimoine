from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.cash_holding import CashHolding

router = APIRouter(prefix="/liquidites")


@router.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    holdings = session.exec(select(CashHolding).order_by(CashHolding.nom)).all()
    return templates.TemplateResponse(
        request, "cash_holdings/liste.html", {"holdings": holdings, "holding_edit": None}
    )


@router.get("/{holding_id}/modifier")
def modifier_formulaire(holding_id: int, request: Request, session: Session = Depends(get_session)):
    holdings = session.exec(select(CashHolding).order_by(CashHolding.nom)).all()
    holding_edit = session.get(CashHolding, holding_id)
    return templates.TemplateResponse(
        request, "cash_holdings/liste.html", {"holdings": holdings, "holding_edit": holding_edit}
    )


@router.post("")
def creer(
    session: Session = Depends(get_session),
    nom: str = Form(...),
    solde: float = Form(...),
    devise: str = Form("EUR"),
):
    holding = CashHolding(nom=nom, solde=solde, devise=devise, date_maj=date.today())
    session.add(holding)
    session.commit()
    return RedirectResponse(url="/liquidites", status_code=303)


@router.post("/{holding_id}")
def modifier(
    holding_id: int,
    session: Session = Depends(get_session),
    nom: str = Form(...),
    solde: float = Form(...),
    devise: str = Form("EUR"),
):
    holding = session.get(CashHolding, holding_id)
    if holding is None:
        return RedirectResponse(url="/liquidites", status_code=303)
    holding.nom = nom
    holding.solde = solde
    holding.devise = devise
    holding.date_maj = date.today()
    session.add(holding)
    session.commit()
    return RedirectResponse(url="/liquidites", status_code=303)


@router.post("/{holding_id}/supprimer")
def supprimer(holding_id: int, session: Session = Depends(get_session)):
    holding = session.get(CashHolding, holding_id)
    if holding is not None:
        session.delete(holding)
        session.commit()
    return RedirectResponse(url="/liquidites", status_code=303)
