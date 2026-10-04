"""Suivi réglementaire du PEA : versements cumulés vs plafond, ancienneté.

Le plafond de versements porte sur les dépôts/retraits, jamais sur la
valorisation du compte (c'est la règle PEA) — voir `versements_cumules`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, select

from ..fiscal.loader import FiscalParams
from ..models.enums import TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction


@dataclass
class SuiviPea:
    versements_cumules: float
    plafond: float
    marge_disponible: float
    anciennete_annees: float | None
    anciennete_suffisante: bool | None


def versements_cumules(session: Session, account_id: int) -> float:
    transactions = session.exec(
        select(InvestmentTransaction).where(InvestmentTransaction.account_id == account_id)
    ).all()
    total = 0.0
    for t in transactions:
        if t.type == TypeTransaction.depot:
            total += t.montant
        elif t.type == TypeTransaction.retrait:
            total -= t.montant
    return total


def compute_suivi_pea(
    session: Session, account: InvestmentAccount, params: FiscalParams, aujourdhui: date | None = None
) -> SuiviPea:
    aujourdhui = aujourdhui or date.today()
    pea_params = params.pea
    plafond = pea_params.plafond_versements if pea_params else 0.0
    versements = versements_cumules(session, account.id)

    anciennete_annees: float | None = None
    anciennete_suffisante: bool | None = None
    if account.date_ouverture is not None:
        anciennete_annees = (aujourdhui - account.date_ouverture).days / 365.25
        if pea_params is not None:
            anciennete_suffisante = anciennete_annees >= pea_params.anciennete_minimale_annees

    return SuiviPea(
        versements_cumules=versements,
        plafond=plafond,
        marge_disponible=plafond - versements,
        anciennete_annees=anciennete_annees,
        anciennete_suffisante=anciennete_suffisante,
    )
