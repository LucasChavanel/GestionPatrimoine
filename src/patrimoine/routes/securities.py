from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.enums import AllocationCategorie
from ..models.security import Security
from ..services.market_data import fetch_price

router = APIRouter(prefix="/titres")


@router.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    securities = session.exec(select(Security).order_by(Security.nom)).all()
    return templates.TemplateResponse(
        request,
        "securities/liste.html",
        {"securities": securities, "security_edit": None, "categories": list(AllocationCategorie)},
    )


@router.get("/{security_id}/modifier")
def modifier_formulaire(security_id: int, request: Request, session: Session = Depends(get_session)):
    securities = session.exec(select(Security).order_by(Security.nom)).all()
    security_edit = session.get(Security, security_id)
    return templates.TemplateResponse(
        request,
        "securities/liste.html",
        {
            "securities": securities,
            "security_edit": security_edit,
            "categories": list(AllocationCategorie),
        },
    )


def _form_to_security(
    security: Security,
    isin: str,
    nom: str,
    ticker_yahoo: str | None,
    categorie_allocation: str | None,
    dernier_cours: str | None,
) -> None:
    security.isin = isin
    security.nom = nom
    security.ticker_yahoo = ticker_yahoo or None
    security.categorie_allocation = AllocationCategorie(categorie_allocation) if categorie_allocation else None
    if dernier_cours:
        security.dernier_cours = float(dernier_cours)
        security.dernier_cours_date = date.today()


@router.post("")
def creer(
    session: Session = Depends(get_session),
    isin: str = Form(...),
    nom: str = Form(...),
    ticker_yahoo: str | None = Form(None),
    categorie_allocation: str | None = Form(None),
    dernier_cours: str | None = Form(None),
):
    security = Security(isin=isin, nom=nom)
    _form_to_security(security, isin, nom, ticker_yahoo, categorie_allocation, dernier_cours)
    session.add(security)
    session.commit()
    return RedirectResponse(url="/titres", status_code=303)


@router.post("/{security_id}")
def modifier(
    security_id: int,
    session: Session = Depends(get_session),
    isin: str = Form(...),
    nom: str = Form(...),
    ticker_yahoo: str | None = Form(None),
    categorie_allocation: str | None = Form(None),
    dernier_cours: str | None = Form(None),
):
    security = session.get(Security, security_id)
    if security is None:
        return RedirectResponse(url="/titres", status_code=303)
    _form_to_security(security, isin, nom, ticker_yahoo, categorie_allocation, dernier_cours)
    session.add(security)
    session.commit()
    return RedirectResponse(url="/titres", status_code=303)


@router.post("/{security_id}/supprimer")
def supprimer(security_id: int, session: Session = Depends(get_session)):
    security = session.get(Security, security_id)
    if security is not None:
        session.delete(security)
        session.commit()
    return RedirectResponse(url="/titres", status_code=303)


@router.post("/{security_id}/rafraichir-cours")
def rafraichir_cours(security_id: int, session: Session = Depends(get_session)):
    security = session.get(Security, security_id)
    if security is not None and security.ticker_yahoo:
        prix = fetch_price(security.ticker_yahoo)
        if prix is not None:
            security.dernier_cours = prix.prix
            security.dernier_cours_devise = prix.devise
            security.dernier_cours_date = date.today()
            session.add(security)
            session.commit()
    return RedirectResponse(url="/titres", status_code=303)
