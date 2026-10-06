from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..fiscal.loader import load_fiscal_params
from ..models.enums import Courtier, EnvelopeType, TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction
from ..models.security import Security
from ..services.allocation import compute_allocation
from ..services.ibkr_credentials import get_credentials
from ..services.ibkr_sync import sync_operations, sync_solde_ouverture
from ..services.market_data import refresh_all_prices
from ..services.pea import compute_suivi_pea
from ..services.positions import compute_positions

router_liste = APIRouter(prefix="/investissements")
router_compte = APIRouter(prefix="/investissements/{account_id}")


def get_account_or_404(account_id: int, session: Session = Depends(get_session)) -> InvestmentAccount:
    account = session.get(InvestmentAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return account


@router_liste.get("")
def liste(request: Request, session: Session = Depends(get_session)):
    accounts = session.exec(select(InvestmentAccount).order_by(InvestmentAccount.nom)).all()
    return templates.TemplateResponse(
        request,
        "investments/liste.html",
        {
            "accounts": accounts,
            "types_enveloppe": list(EnvelopeType),
            "courtiers": list(Courtier),
        },
    )


@router_liste.post("")
def creer(
    session: Session = Depends(get_session),
    nom: str = Form(...),
    type_enveloppe: EnvelopeType = Form(...),
    courtier: Courtier = Form(...),
    devise_base: str = Form("EUR"),
    date_ouverture: str | None = Form(None),
):
    account = InvestmentAccount(
        nom=nom,
        type=type_enveloppe,
        courtier=courtier,
        devise_base=devise_base,
        date_ouverture=date.fromisoformat(date_ouverture) if date_ouverture else None,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return RedirectResponse(url=f"/investissements/{account.id}", status_code=303)


def _fiche_context(session: Session, account: InvestmentAccount, **extra) -> dict:
    positions = compute_positions(session, account.id)
    params = load_fiscal_params(date.today().year)
    suivi_pea = compute_suivi_pea(session, account, params) if account.type == EnvelopeType.pea else None
    allocation = compute_allocation(positions, params) if account.type == EnvelopeType.pea else None
    return {
        "account": account,
        "positions": positions,
        "suivi_pea": suivi_pea,
        "allocation": allocation,
        "ibkr_resultat": None,
        "ibkr_erreur": None,
        "cours_resultat": None,
        **extra,
    }


@router_compte.get("")
def fiche(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    return templates.TemplateResponse(request, "investments/fiche.html", _fiche_context(session, account))


@router_compte.post("/rafraichir-cours")
def rafraichir_cours(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    r = refresh_all_prices(session)
    resultat = f"{r.mis_a_jour} cours mis à jour, {r.echecs} échec(s)."
    if r.tickers_resolus:
        resultat += f" {r.tickers_resolus} ticker(s) Yahoo résolu(s) automatiquement depuis l'ISIN."
    if r.sans_ticker:
        resultat += f" {r.sans_ticker} titre(s) sans ticker Yahoo trouvé (voir /titres pour le renseigner manuellement)."
    context = _fiche_context(session, account, cours_resultat=resultat)
    return templates.TemplateResponse(request, "investments/fiche.html", context)


@router_compte.post("")
def enregistrer(
    account_id: int,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
    nom: str = Form(...),
    type_enveloppe: EnvelopeType = Form(...),
    courtier: Courtier = Form(...),
    devise_base: str = Form("EUR"),
    date_ouverture: str | None = Form(None),
):
    account.nom = nom
    account.type = type_enveloppe
    account.courtier = courtier
    account.devise_base = devise_base
    account.date_ouverture = date.fromisoformat(date_ouverture) if date_ouverture else None
    session.add(account)
    session.commit()
    return RedirectResponse(url=f"/investissements/{account_id}", status_code=303)


@router_compte.post("/ibkr/solde-ouverture")
def ibkr_solde_ouverture(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    r = sync_solde_ouverture(session, account, get_credentials())
    if r.erreur:
        context = _fiche_context(session, account, ibkr_erreur=r.erreur)
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    resultat = f"{r.importees} position(s) importée(s), {r.deja_presentes} déjà présente(s) (ignorée(s))."
    if r.depots_corriges:
        resultat += f" {r.depots_corriges} dépôt(s) d'ouverture manquant(s) corrigé(s) rétroactivement."
    context = _fiche_context(session, account, ibkr_resultat=resultat)
    return templates.TemplateResponse(request, "investments/fiche.html", context)


@router_compte.post("/ibkr/synchroniser")
def ibkr_synchroniser(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    r = sync_operations(session, account, get_credentials())
    if r.erreur:
        context = _fiche_context(session, account, ibkr_erreur=r.erreur)
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    resultat = f"{r.importees} opération(s) importée(s), {r.deja_presentes} déjà présente(s) (ignorée(s))."
    if r.types_ignores:
        detail = ", ".join(f"{t} (x{n})" for t, n in r.types_ignores.items())
        resultat += f" Types IBKR non gérés ignorés : {detail}."
    context = _fiche_context(session, account, ibkr_resultat=resultat)
    return templates.TemplateResponse(request, "investments/fiche.html", context)


@router_compte.get("/operations")
def operations(
    account_id: int,
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    transactions = session.exec(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.account_id == account_id)
        .order_by(InvestmentTransaction.date.desc())
    ).all()
    securities = session.exec(select(Security).order_by(Security.nom)).all()
    return templates.TemplateResponse(
        request,
        "investments/operations.html",
        {
            "account": account,
            "transactions": transactions,
            "securities": securities,
            "types_transaction": list(TypeTransaction),
            "transaction_edit": None,
        },
    )


@router_compte.get("/operations/{transaction_id}/modifier")
def modifier_formulaire(
    account_id: int,
    transaction_id: int,
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    transaction_edit = session.get(InvestmentTransaction, transaction_id)
    transactions = session.exec(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.account_id == account_id)
        .order_by(InvestmentTransaction.date.desc())
    ).all()
    securities = session.exec(select(Security).order_by(Security.nom)).all()
    return templates.TemplateResponse(
        request,
        "investments/operations.html",
        {
            "account": account,
            "transactions": transactions,
            "securities": securities,
            "types_transaction": list(TypeTransaction),
            "transaction_edit": transaction_edit,
        },
    )


def _parse_security_id(security_id: str | None) -> int | None:
    return int(security_id) if security_id else None


def _parse_float(value: str | None) -> float | None:
    return float(value) if value else None


@router_compte.post("/operations")
def creer_operation(
    account_id: int,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
    date_: str = Form(..., alias="date"),
    type_transaction: TypeTransaction = Form(...),
    security_id: str | None = Form(None),
    quantite: str | None = Form(None),
    prix_unitaire: str | None = Form(None),
    devise: str = Form("EUR"),
    frais: float = Form(0.0),
    montant: float = Form(...),
    description: str | None = Form(None),
):
    transaction = InvestmentTransaction(
        account_id=account_id,
        security_id=_parse_security_id(security_id),
        date=date.fromisoformat(date_),
        type=type_transaction,
        quantite=_parse_float(quantite),
        prix_unitaire=_parse_float(prix_unitaire),
        devise=devise,
        frais=frais,
        montant=montant,
        description=description or None,
    )
    session.add(transaction)
    session.commit()
    return RedirectResponse(url=f"/investissements/{account_id}/operations", status_code=303)


@router_compte.post("/operations/{transaction_id}")
def modifier_operation(
    account_id: int,
    transaction_id: int,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
    date_: str = Form(..., alias="date"),
    type_transaction: TypeTransaction = Form(...),
    security_id: str | None = Form(None),
    quantite: str | None = Form(None),
    prix_unitaire: str | None = Form(None),
    devise: str = Form("EUR"),
    frais: float = Form(0.0),
    montant: float = Form(...),
    description: str | None = Form(None),
):
    transaction = session.get(InvestmentTransaction, transaction_id)
    if transaction is None:
        return RedirectResponse(url=f"/investissements/{account_id}/operations", status_code=303)
    transaction.date = date.fromisoformat(date_)
    transaction.type = type_transaction
    transaction.security_id = _parse_security_id(security_id)
    transaction.quantite = _parse_float(quantite)
    transaction.prix_unitaire = _parse_float(prix_unitaire)
    transaction.devise = devise
    transaction.frais = frais
    transaction.montant = montant
    transaction.description = description or None
    session.add(transaction)
    session.commit()
    return RedirectResponse(url=f"/investissements/{account_id}/operations", status_code=303)


@router_compte.post("/operations/{transaction_id}/supprimer")
def supprimer_operation(
    account_id: int,
    transaction_id: int,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    transaction = session.get(InvestmentTransaction, transaction_id)
    if transaction is not None:
        session.delete(transaction)
        session.commit()
    return RedirectResponse(url=f"/investissements/{account_id}/operations", status_code=303)
