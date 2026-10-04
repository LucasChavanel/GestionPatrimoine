from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..models.enums import Courtier, EnvelopeType, TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction
from ..models.security import Security
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


@router_compte.get("")
def fiche(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    positions = compute_positions(session, account.id)
    return templates.TemplateResponse(
        request,
        "investments/fiche.html",
        {"account": account, "positions": positions},
    )


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
