"""Positions calculées à partir des InvestmentTransaction — jamais stockées,
une seule source de vérité (même principe que services/simulator.py pour le
fiscal : recalculé à la demande, pas d'état à invalider)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlmodel import Session, select

from ..models.enums import TypeTransaction
from ..models.investment_transaction import InvestmentTransaction
from ..models.security import Security


@dataclass
class PositionCalculee:
    security: Security
    quantite_detenue: float
    prmp: float
    montant_investi: float


def compute_positions(session: Session, account_id: int) -> list[PositionCalculee]:
    transactions = session.exec(
        select(InvestmentTransaction)
        .where(InvestmentTransaction.account_id == account_id)
        .where(InvestmentTransaction.security_id.is_not(None))
        .order_by(InvestmentTransaction.date)
    ).all()

    par_titre: dict[int, list[InvestmentTransaction]] = defaultdict(list)
    for t in transactions:
        par_titre[t.security_id].append(t)

    positions: list[PositionCalculee] = []
    for security_id, txs in par_titre.items():
        security = session.get(Security, security_id)
        if security is None:
            continue

        quantite_detenue = 0.0
        cout_total = 0.0
        for t in txs:
            if t.type == TypeTransaction.achat and t.quantite:
                cout_total += t.quantite * (t.prix_unitaire or 0.0) + t.frais
                quantite_detenue += t.quantite
            elif t.type == TypeTransaction.vente and t.quantite:
                if quantite_detenue > 0:
                    prmp_courant = cout_total / quantite_detenue
                    cout_total -= min(t.quantite, quantite_detenue) * prmp_courant
                quantite_detenue -= t.quantite
                if quantite_detenue <= 0:
                    quantite_detenue = 0.0
                    cout_total = 0.0

        if quantite_detenue > 0:
            prmp = cout_total / quantite_detenue
            positions.append(
                PositionCalculee(
                    security=security,
                    quantite_detenue=quantite_detenue,
                    prmp=prmp,
                    montant_investi=cout_total,
                )
            )

    return positions
