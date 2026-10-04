"""Synthèse annuelle par bien : vue de rapprochement (recettes, charges brutes par
catégorie, fonds de travaux cumulé, amortissements) — ce n'est pas un calcul
fiscal, voir services/simulator.py pour ça. Les montants ici sont bruts, non
filtrés par déductibilité : l'objectif est de retrouver les chiffres saisis
face aux relevés reçus (syndic, etc.)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..models.booking import Booking
from ..models.enums import CategorieCharge, StatutBooking
from ..models.expense import Expense
from ..models.property import Property
from .simulator import simulate_year


@dataclass
class SyntheseAnnuelle:
    annee: int
    recettes_annee: float
    charges_par_categorie: dict[str, float] = field(default_factory=dict)
    total_charges_annee: float = 0.0
    total_recuperable_annee: float = 0.0
    fonds_travaux_cumule: float = 0.0
    amortissements_deduits_annee: float = 0.0
    cumul_amortissements_pratiques: float = 0.0


def compute_synthese(session: Session, property_: Property, annee: int) -> SyntheseAnnuelle:
    bookings = session.exec(select(Booking).where(Booking.property_id == property_.id)).all()
    recettes_annee = sum(
        b.montant_brut
        for b in bookings
        if b.statut == StatutBooking.confirmee
        and b.date_paiement is not None
        and b.date_paiement.year == annee
    )

    expenses = session.exec(select(Expense).where(Expense.property_id == property_.id)).all()
    expenses_annee = [e for e in expenses if e.date_paiement.year == annee]

    charges_par_categorie: dict[str, float] = defaultdict(float)
    total_recuperable = 0.0
    for e in expenses_annee:
        charges_par_categorie[e.categorie.value] += e.montant_ttc
        total_recuperable += e.montant_recuperable

    fonds_travaux_cumule = sum(
        e.montant_ttc
        for e in expenses
        if e.categorie == CategorieCharge.fonds_travaux and e.date_paiement.year <= annee
    )

    # Réutilise le moteur LMNP déjà testé pour les amortissements (tmi=0 : seuls
    # les montants d'amortissement nous intéressent ici, pas l'impôt).
    reel = simulate_year(session, property_, annee, tmi=0.0).reel

    return SyntheseAnnuelle(
        annee=annee,
        recettes_annee=recettes_annee,
        charges_par_categorie=dict(charges_par_categorie),
        total_charges_annee=sum(charges_par_categorie.values()),
        total_recuperable_annee=total_recuperable,
        fonds_travaux_cumule=fonds_travaux_cumule,
        amortissements_deduits_annee=reel.amortissements_deduits_annee,
        cumul_amortissements_pratiques=reel.cumul_amortissements_pratiques,
    )
