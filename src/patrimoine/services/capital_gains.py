"""Plus-values réalisées et dividendes du CTO, en EUR, pour le récapitulatif
de déclaration (SPEC Phase 4). Limité aux comptes `EnvelopeType.cto` — le PEA
a un régime de différé d'imposition totalement différent (rien n'est
imposable tant qu'il n'y a pas de retrait), hors périmètre de ce calcul annuel.

Même principe que services/positions.py (rejeu chronologique, PRMP, jamais
d'état stocké), mais chaque montant est converti en EUR à la date exacte de
l'opération (services/ecb_rates.py) plutôt qu'en devise native — c'est ce que
demande le calcul fiscal français d'une plus-value sur titres étrangers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..models.enums import EnvelopeType, TypeTransaction
from ..models.investment_account import InvestmentAccount
from ..models.investment_transaction import InvestmentTransaction
from .ecb_rates import to_eur


@dataclass
class PlusValueCto:
    plus_value_annee: float = 0.0
    avertissements: list[str] = field(default_factory=list)


@dataclass
class DividendesCto:
    dividendes_bruts: float = 0.0
    retenues_source: float = 0.0
    avertissements: list[str] = field(default_factory=list)


def _comptes_cto(session: Session) -> list[InvestmentAccount]:
    return session.exec(
        select(InvestmentAccount).where(InvestmentAccount.type == EnvelopeType.cto)
    ).all()


def compute_plus_values_cto(session: Session, annee: int) -> PlusValueCto:
    resultat = PlusValueCto()
    comptes = _comptes_cto(session)
    if not comptes:
        return resultat

    for compte in comptes:
        transactions = session.exec(
            select(InvestmentTransaction)
            .where(InvestmentTransaction.account_id == compte.id)
            .where(InvestmentTransaction.security_id.is_not(None))
            .order_by(InvestmentTransaction.date)
        ).all()

        par_titre: dict[int, list[InvestmentTransaction]] = defaultdict(list)
        for t in transactions:
            par_titre[t.security_id].append(t)

        for txs in par_titre.values():
            quantite_detenue = 0.0
            cout_total_eur = 0.0
            for t in txs:
                if t.type == TypeTransaction.achat and t.quantite:
                    cout_natif = t.quantite * (t.prix_unitaire or 0.0) + t.frais
                    cout_eur = to_eur(cout_natif, t.devise, t.date)
                    if cout_eur is None:
                        resultat.avertissements.append(
                            f"Conversion BCE indisponible pour l'achat du {t.date} "
                            f"({compte.nom}) — exclu du calcul."
                        )
                        continue
                    cout_total_eur += cout_eur
                    quantite_detenue += t.quantite

                elif t.type == TypeTransaction.vente and t.quantite:
                    produit_eur = to_eur(t.montant - t.frais, t.devise, t.date)
                    if produit_eur is None:
                        resultat.avertissements.append(
                            f"Conversion BCE indisponible pour la vente du {t.date} "
                            f"({compte.nom}) — exclue du calcul."
                        )
                        quantite_detenue = max(0.0, quantite_detenue - t.quantite)
                        continue

                    if quantite_detenue > 0:
                        prmp_eur = cout_total_eur / quantite_detenue
                        quantite_vendue = min(t.quantite, quantite_detenue)
                        cout_cede_eur = quantite_vendue * prmp_eur
                        if t.date.year == annee:
                            resultat.plus_value_annee += produit_eur - cout_cede_eur
                        cout_total_eur -= cout_cede_eur
                    quantite_detenue -= t.quantite
                    if quantite_detenue <= 0:
                        quantite_detenue = 0.0
                        cout_total_eur = 0.0

    return resultat


def compute_dividendes_cto(session: Session, annee: int) -> DividendesCto:
    resultat = DividendesCto()
    comptes = _comptes_cto(session)
    if not comptes:
        return resultat

    for compte in comptes:
        transactions = session.exec(
            select(InvestmentTransaction)
            .where(InvestmentTransaction.account_id == compte.id)
            .where(InvestmentTransaction.type.in_([TypeTransaction.dividende, TypeTransaction.retenue_source]))
        ).all()
        for t in transactions:
            if t.date.year != annee:
                continue
            montant_eur = to_eur(t.montant, t.devise, t.date)
            if montant_eur is None:
                resultat.avertissements.append(
                    f"Conversion BCE indisponible pour l'opération du {t.date} ({compte.nom}) — exclue du calcul."
                )
                continue
            if t.type == TypeTransaction.dividende:
                resultat.dividendes_bruts += montant_eur
            else:
                resultat.retenues_source += montant_eur

    return resultat
