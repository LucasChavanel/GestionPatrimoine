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
from ..services import ibkr_flex
from ..services.allocation import compute_allocation
from ..services.ibkr_credentials import get_credentials
from ..services.market_data import fetch_price
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
    account_id: int,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    positions = compute_positions(session, account.id)
    for position in positions:
        security = position.security
        if not security.ticker_yahoo:
            continue
        prix = fetch_price(security.ticker_yahoo)
        if prix is not None:
            security.dernier_cours = prix.prix
            security.dernier_cours_devise = prix.devise
            security.dernier_cours_date = date.today()
            session.add(security)
    session.commit()
    return RedirectResponse(url=f"/investissements/{account_id}", status_code=303)


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


def _get_or_create_security(session: Session, isin: str, nom: str) -> Security | None:
    if not isin:
        return None
    security = session.exec(select(Security).where(Security.isin == isin)).first()
    if security is None:
        security = Security(isin=isin, nom=nom or isin)
        session.add(security)
        session.commit()
        session.refresh(security)
    return security


def _transaction_existe(session: Session, account_id: int, external_id: str) -> bool:
    existing = session.exec(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.account_id == account_id)
        .where(InvestmentTransaction.external_id == external_id)
    ).first()
    return existing is not None


@router_compte.post("/ibkr/solde-ouverture")
def ibkr_solde_ouverture(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    creds = get_credentials()
    if not creds.token or not creds.query_id:
        context = _fiche_context(
            session, account, ibkr_erreur="Identifiants IBKR non configurés (voir /parametres)."
        )
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    try:
        xml_text = ibkr_flex.fetch_report(creds.token, creds.query_id)
    except ibkr_flex.IbkrFlexError as exc:
        context = _fiche_context(session, account, ibkr_erreur=str(exc))
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    positions = ibkr_flex.parse_open_positions(xml_text)
    importees = 0
    deja_presentes = 0
    for position in positions:
        external_id = f"ibkr-position-{position.conid}"
        if _transaction_existe(session, account.id, external_id):
            deja_presentes += 1
            continue
        security = _get_or_create_security(session, position.isin, position.symbol)
        transaction = InvestmentTransaction(
            account_id=account.id,
            security_id=security.id if security else None,
            date=date.today(),
            type=TypeTransaction.achat,
            quantite=position.quantite,
            prix_unitaire=position.prix_moyen,
            devise=position.devise,
            frais=0.0,
            montant=position.quantite * position.prix_moyen,
            description="Import IBKR — solde d'ouverture",
            external_id=external_id,
        )
        session.add(transaction)
        importees += 1
    session.commit()

    resultat = f"{importees} position(s) importée(s), {deja_presentes} déjà présente(s) (ignorée(s))."
    context = _fiche_context(session, account, ibkr_resultat=resultat)
    return templates.TemplateResponse(request, "investments/fiche.html", context)


@router_compte.post("/ibkr/synchroniser")
def ibkr_synchroniser(
    request: Request,
    session: Session = Depends(get_session),
    account: InvestmentAccount = Depends(get_account_or_404),
):
    creds = get_credentials()
    if not creds.token or not creds.query_id:
        context = _fiche_context(
            session, account, ibkr_erreur="Identifiants IBKR non configurés (voir /parametres)."
        )
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    try:
        xml_text = ibkr_flex.fetch_report(creds.token, creds.query_id)
    except ibkr_flex.IbkrFlexError as exc:
        context = _fiche_context(session, account, ibkr_erreur=str(exc))
        return templates.TemplateResponse(request, "investments/fiche.html", context)

    importees = 0
    deja_presentes = 0
    types_ignores: dict[str, int] = {}

    for cash_tx in ibkr_flex.parse_cash_transactions(xml_text):
        external_id = f"ibkr-{cash_tx.transaction_id}"
        if _transaction_existe(session, account.id, external_id):
            deja_presentes += 1
            continue
        type_mappe = ibkr_flex.map_cash_transaction_type(cash_tx.type_brut, cash_tx.montant)
        if type_mappe is None:
            types_ignores[cash_tx.type_brut] = types_ignores.get(cash_tx.type_brut, 0) + 1
            continue
        transaction = InvestmentTransaction(
            account_id=account.id,
            security_id=None,
            date=cash_tx.date,
            type=type_mappe,
            devise=cash_tx.devise,
            montant=abs(cash_tx.montant),
            description=cash_tx.description or f"Import IBKR — {cash_tx.type_brut}",
            external_id=external_id,
        )
        session.add(transaction)
        importees += 1

    for trade in ibkr_flex.parse_trades(xml_text):
        external_id = f"ibkr-{trade.trade_id}"
        if _transaction_existe(session, account.id, external_id):
            deja_presentes += 1
            continue
        security = _get_or_create_security(session, trade.isin, trade.symbol)
        transaction = InvestmentTransaction(
            account_id=account.id,
            security_id=security.id if security else None,
            date=trade.date,
            type=TypeTransaction.achat if trade.achat else TypeTransaction.vente,
            quantite=trade.quantite,
            prix_unitaire=trade.prix,
            devise=trade.devise,
            frais=trade.frais,
            montant=trade.quantite * trade.prix,
            description="Import IBKR — trade",
            external_id=external_id,
        )
        session.add(transaction)
        importees += 1

    session.commit()

    resultat = f"{importees} opération(s) importée(s), {deja_presentes} déjà présente(s) (ignorée(s))."
    if types_ignores:
        detail = ", ".join(f"{t} (x{n})" for t, n in types_ignores.items())
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
