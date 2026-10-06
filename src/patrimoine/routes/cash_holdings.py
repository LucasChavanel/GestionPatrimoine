from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.cash_holding import CashHolding

router = APIRouter(prefix="/liquidites")


def _parse_optional_float(value: str | None) -> float | None:
    if not value:
        return None
    return float(value)


def _parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


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


def _form_to_holding(
    holding: CashHolding,
    nom: str,
    solde: float,
    devise: str,
    taux_pct: str | None,
    duree_mois: str | None,
    date_fin: str | None,
) -> None:
    holding.nom = nom
    holding.solde = solde
    holding.devise = devise
    holding.date_maj = date.today()
    holding.taux_pct = _parse_optional_float(taux_pct)
    holding.duree_mois = _parse_optional_int(duree_mois)
    holding.date_fin = _parse_optional_date(date_fin)


@router.post("")
def creer(
    session: Session = Depends(get_session),
    nom: str = Form(...),
    solde: float = Form(...),
    devise: str = Form("EUR"),
    taux_pct: str | None = Form(None),
    duree_mois: str | None = Form(None),
    date_fin: str | None = Form(None),
):
    holding = CashHolding(nom=nom, solde=solde, devise=devise, date_maj=date.today())
    _form_to_holding(holding, nom, solde, devise, taux_pct, duree_mois, date_fin)
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
    taux_pct: str | None = Form(None),
    duree_mois: str | None = Form(None),
    date_fin: str | None = Form(None),
):
    holding = session.get(CashHolding, holding_id)
    if holding is None:
        return RedirectResponse(url="/liquidites", status_code=303)
    _form_to_holding(holding, nom, solde, devise, taux_pct, duree_mois, date_fin)
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
