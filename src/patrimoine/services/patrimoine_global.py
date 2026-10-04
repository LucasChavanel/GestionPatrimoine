"""Dashboard consolidé (Phase 5) : agrège tout ce qui existe déjà — positions
calculées, biens immobiliers, cash — sans rien stocker de redondant, à
l'exception du snapshot quotidien qui sert d'historique (voir
enregistrer_snapshot_du_jour)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, select

from ..fiscal.loader import FiscalParams
from ..models.cash_holding import CashHolding
from ..models.enums import AllocationCategorie, TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction
from ..models.patrimoine_snapshot import PatrimoineSnapshot
from ..models.property import Property
from .positions import compute_positions


def cash_disponible(session: Session, account: InvestmentAccount) -> float:
    """Cash non investi dans l'enveloppe, dérivé de l'historique des transactions
    (jamais stocké — même principe que compute_positions). `change` est ignoré
    (simplification assumée : une conversion de devise a deux jambes, non
    modélisées séparément aujourd'hui)."""
    transactions = session.exec(
        select(InvestmentTransaction).where(InvestmentTransaction.account_id == account.id)
    ).all()
    solde = 0.0
    for t in transactions:
        if t.type == TypeTransaction.depot:
            solde += t.montant
        elif t.type == TypeTransaction.retrait:
            solde -= t.montant
        elif t.type == TypeTransaction.achat:
            solde -= t.montant + t.frais
        elif t.type == TypeTransaction.vente:
            solde += t.montant - t.frais
        elif t.type in (TypeTransaction.dividende, TypeTransaction.interet):
            solde += t.montant
        elif t.type in (TypeTransaction.frais, TypeTransaction.retenue_source):
            solde -= t.montant
        # TypeTransaction.change : ignoré, voir docstring.
    return solde


def _valeur_position(position) -> float:
    cours = position.security.dernier_cours
    if cours is None:
        return position.montant_investi
    return position.quantite_detenue * cours


@dataclass
class PatrimoineConsolide:
    valeur_world: float = 0.0
    valeur_europe: float = 0.0
    valeur_emergents: float = 0.0
    valeur_actions_autre: float = 0.0
    valeur_or: float = 0.0
    valeur_cash: float = 0.0
    valeur_immobilier: float = 0.0
    pct_us: float | None = None
    pct_europe: float | None = None
    pct_emergents: float | None = None
    details_biens: list[dict] = field(default_factory=list)

    @property
    def valeur_actions(self) -> float:
        return self.valeur_world + self.valeur_europe + self.valeur_emergents + self.valeur_actions_autre

    @property
    def valeur_totale(self) -> float:
        return self.valeur_actions + self.valeur_cash + self.valeur_immobilier + self.valeur_or


def compute_consolide(session: Session, params: FiscalParams) -> PatrimoineConsolide:
    consolide = PatrimoineConsolide()

    accounts = session.exec(select(InvestmentAccount)).all()
    for account in accounts:
        consolide.valeur_cash += cash_disponible(session, account)
        for position in compute_positions(session, account.id):
            valeur = _valeur_position(position)
            categorie = position.security.categorie_allocation
            if categorie == AllocationCategorie.world:
                consolide.valeur_world += valeur
            elif categorie == AllocationCategorie.europe:
                consolide.valeur_europe += valeur
            elif categorie == AllocationCategorie.emergents:
                consolide.valeur_emergents += valeur
            elif categorie == AllocationCategorie.or_metal:
                consolide.valeur_or += valeur
            else:
                consolide.valeur_actions_autre += valeur

    for holding in session.exec(select(CashHolding)).all():
        consolide.valeur_cash += holding.solde

    for property_ in session.exec(select(Property)).all():
        valeur = property_.valeur_estimee if property_.valeur_estimee is not None else property_.prix_acquisition
        valeur_quote_part = valeur * property_.quote_part
        consolide.valeur_immobilier += valeur_quote_part
        consolide.details_biens.append({"nom": property_.nom, "valeur": valeur_quote_part})

    valeur_actions = consolide.valeur_actions
    if valeur_actions > 0 and params.patrimoine_global is not None:
        pg = params.patrimoine_global
        consolide.pct_us = (consolide.valeur_world * pg.part_us_dans_world) / valeur_actions
        consolide.pct_europe = (
            consolide.valeur_europe + consolide.valeur_world * pg.part_europe_dans_world
        ) / valeur_actions
        consolide.pct_emergents = consolide.valeur_emergents / valeur_actions

    return consolide


def enregistrer_snapshot_du_jour(session: Session, consolide: PatrimoineConsolide) -> PatrimoineSnapshot:
    aujourdhui = date.today()
    snapshot = session.exec(
        select(PatrimoineSnapshot).where(PatrimoineSnapshot.date_snapshot == aujourdhui)
    ).first()
    if snapshot is None:
        snapshot = PatrimoineSnapshot(date_snapshot=aujourdhui, valeur_actions=0, valeur_cash=0,
                                       valeur_immobilier=0, valeur_or=0, valeur_totale=0)
    snapshot.valeur_actions = consolide.valeur_actions
    snapshot.valeur_cash = consolide.valeur_cash
    snapshot.valeur_immobilier = consolide.valeur_immobilier
    snapshot.valeur_or = consolide.valeur_or
    snapshot.valeur_totale = consolide.valeur_totale
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot
