from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.enums import AllocationCategorie
from ..models.security import Security
from ..services.market_data import fetch_price, refresh_all_prices

router = APIRouter(prefix="/titres")


def _liste_context(session: Session, **extra) -> dict:
    securities = session.exec(select(Security).order_by(Security.nom)).all()
    return {
        "securities": securities,
        "security_edit": None,
        "categories": list(AllocationCategorie),
        "resultat": None,
        **extra,
    }


@router.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "securities/liste.html", _liste_context(session))


@router.get("/{security_id}/modifier")
def modifier_formulaire(security_id: int, request: Request, session: Session = Depends(get_session)):
    security_edit = session.get(Security, security_id)
    context = _liste_context(session, security_edit=security_edit)
    return templates.TemplateResponse(request, "securities/liste.html", context)


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


@router.post("/rafraichir-tout")
def rafraichir_tout(request: Request, session: Session = Depends(get_session)):
    r = refresh_all_prices(session)
    resultat = f"{r.mis_a_jour} cours mis à jour, {r.echecs} échec(s)."
    if r.sans_ticker:
        resultat += f" {r.sans_ticker} titre(s) sans ticker Yahoo renseigné."
    context = _liste_context(session, resultat=resultat)
    return templates.TemplateResponse(request, "securities/liste.html", context)


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
def rafraichir_cours(security_id: int, request: Request, session: Session = Depends(get_session)):
    security = session.get(Security, security_id)
    if security is None:
        return RedirectResponse(url="/titres", status_code=303)
    if not security.ticker_yahoo:
        resultat = f"{security.nom} : aucun ticker Yahoo renseigné, impossible de récupérer un cours."
    else:
        prix = fetch_price(security.ticker_yahoo)
        if prix is None:
            resultat = (
                f"{security.nom} ({security.ticker_yahoo}) : échec de la récupération du cours "
                "(ticker invalide, réseau indisponible, ou Yahoo Finance injoignable)."
            )
        else:
            security.dernier_cours = prix.prix
            security.dernier_cours_devise = prix.devise
            security.dernier_cours_date = date.today()
            session.add(security)
            session.commit()
            resultat = f"{security.nom} : cours mis à jour ({prix.prix} {prix.devise})."
    context = _liste_context(session, resultat=resultat)
    return templates.TemplateResponse(request, "securities/liste.html", context)
