"""Import des positions/opérations IBKR — logique partagée entre les routes
(clic manuel, voir routes/investments.py) et le rafraîchissement automatique
au lancement (voir main.py::run). Aucune dépendance à FastAPI/Jinja ici :
ces fonctions prennent une Session et retournent un résultat typé, à charge
de l'appelant de l'afficher (page re-rendue) ou de le journaliser (lancement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, select

from ..models.enums import TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction
from ..models.security import Security
from . import ibkr_flex
from .ibkr_credentials import IbkrCredentials
from .market_data import resolve_ticker_from_isin


def get_or_create_security(session: Session, isin: str, nom: str) -> Security | None:
    if not isin:
        return None
    security = session.exec(select(Security).where(Security.isin == isin)).first()
    if security is None:
        security = Security(isin=isin, nom=nom or isin, ticker_yahoo=resolve_ticker_from_isin(isin))
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


@dataclass
class SoldeOuvertureResultat:
    importees: int = 0
    deja_presentes: int = 0
    depots_corriges: int = 0
    erreur: str | None = None


def sync_solde_ouverture(
    session: Session, account: InvestmentAccount, creds: IbkrCredentials
) -> SoldeOuvertureResultat:
    resultat = SoldeOuvertureResultat()
    if not creds.token or not creds.query_id:
        resultat.erreur = "Identifiants IBKR non configurés (voir /parametres)."
        return resultat

    try:
        xml_text = ibkr_flex.fetch_report(creds.token, creds.query_id)
    except ibkr_flex.IbkrFlexError as exc:
        resultat.erreur = str(exc)
        return resultat

    for position in ibkr_flex.parse_open_positions(xml_text):
        external_id = f"ibkr-position-{position.conid}"
        depot_external_id = f"ibkr-depot-ouverture-{position.conid}"
        montant = position.quantite * position.prix_moyen

        achat_existe = _transaction_existe(session, account.id, external_id)
        if not achat_existe:
            security = get_or_create_security(session, position.isin, position.symbol)
            session.add(
                InvestmentTransaction(
                    account_id=account.id,
                    security_id=security.id if security else None,
                    date=date.today(),
                    type=TypeTransaction.achat,
                    quantite=position.quantite,
                    prix_unitaire=position.prix_moyen,
                    devise=position.devise,
                    frais=0.0,
                    montant=montant,
                    description="Import IBKR — solde d'ouverture",
                    external_id=external_id,
                )
            )
            resultat.importees += 1
        else:
            resultat.deja_presentes += 1

        # Dépôt synthétique de même montant : l'historique réel des versements
        # qui ont financé cette position n'est pas récupérable via Flex, donc
        # sans cette ligne l'achat ferait passer le cash calculé largement
        # négatif — un solde d'ouverture n'est pas un découvert. Backfill si
        # l'achat a été importé avant ce correctif.
        if not _transaction_existe(session, account.id, depot_external_id):
            session.add(
                InvestmentTransaction(
                    account_id=account.id,
                    date=date.today(),
                    type=TypeTransaction.depot,
                    devise=position.devise,
                    montant=montant,
                    description="Import IBKR — dépôt synthétique associé au solde d'ouverture",
                    external_id=depot_external_id,
                )
            )
            if achat_existe:
                resultat.depots_corriges += 1
    session.commit()
    return resultat


@dataclass
class SyncOperationsResultat:
    importees: int = 0
    deja_presentes: int = 0
    types_ignores: dict[str, int] = field(default_factory=dict)
    erreur: str | None = None


def sync_operations(
    session: Session, account: InvestmentAccount, creds: IbkrCredentials
) -> SyncOperationsResultat:
    resultat = SyncOperationsResultat()
    if not creds.token or not creds.query_id:
        resultat.erreur = "Identifiants IBKR non configurés (voir /parametres)."
        return resultat

    try:
        xml_text = ibkr_flex.fetch_report(creds.token, creds.query_id)
    except ibkr_flex.IbkrFlexError as exc:
        resultat.erreur = str(exc)
        return resultat

    for cash_tx in ibkr_flex.parse_cash_transactions(xml_text):
        external_id = f"ibkr-{cash_tx.transaction_id}"
        if _transaction_existe(session, account.id, external_id):
            resultat.deja_presentes += 1
            continue
        type_mappe = ibkr_flex.map_cash_transaction_type(cash_tx.type_brut, cash_tx.montant)
        if type_mappe is None:
            resultat.types_ignores[cash_tx.type_brut] = resultat.types_ignores.get(cash_tx.type_brut, 0) + 1
            continue
        session.add(
            InvestmentTransaction(
                account_id=account.id,
                security_id=None,
                date=cash_tx.date,
                type=type_mappe,
                devise=cash_tx.devise,
                montant=abs(cash_tx.montant),
                description=cash_tx.description or f"Import IBKR — {cash_tx.type_brut}",
                external_id=external_id,
            )
        )
        resultat.importees += 1

    for trade in ibkr_flex.parse_trades(xml_text):
        external_id = f"ibkr-{trade.trade_id}"
        if _transaction_existe(session, account.id, external_id):
            resultat.deja_presentes += 1
            continue
        security = get_or_create_security(session, trade.isin, trade.symbol)
        session.add(
            InvestmentTransaction(
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
        )
        resultat.importees += 1

    session.commit()
    return resultat
