"""Moteur d'amortissement linéaire au prorata en jours.

Décisions prises avec l'utilisateur (voir conversation / plan) :
- Prorata en jours sur toute la durée de vie de l'actif (1er ET dernier exercice
  proratisés), taux journalier = base / (durée_ans × 365).
- Les travaux d'amélioration/construction réalisés avant la première mise en
  location s'intègrent à la base amortissable du bâti (répartis sur les
  BuildingComponent), plutôt que d'être amortis séparément.
- Le mobilier sous le seuil (fichier fiscal de l'année d'achat) est une charge
  directe, pas un amortissement — voir routes/expenses.py pour la décision
  prise à la saisie (Immobilisation créée ou non).
"""

from __future__ import annotations

from datetime import date, timedelta

from ..fiscal.loader import FiscalParams
from ..models.enums import NatureImmobilisation
from ..models.immobilisation import Immobilisation
from ..models.property import BuildingComponent, Property

JOURS_PAR_AN = 365


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # 29 février -> pas d'équivalent une année non bissextile
        return d.replace(year=d.year + years, day=28)


def dotation_annuelle(base: float, duree_ans: int, date_debut: date, annee: int) -> float:
    """Dotation d'amortissement pour `annee`. Retourne 0 hors de la fenêtre
    [date_debut, date_debut + duree_ans ans)."""
    if duree_ans <= 0 or base <= 0:
        return 0.0

    taux_journalier = base / (duree_ans * JOURS_PAR_AN)

    debut_fenetre = date_debut
    fin_fenetre_incluse = _add_years(date_debut, duree_ans) - timedelta(days=1)

    debut_annee = date(annee, 1, 1)
    fin_annee = date(annee, 12, 31)

    debut_intersection = max(debut_fenetre, debut_annee)
    fin_intersection = min(fin_fenetre_incluse, fin_annee)

    if debut_intersection > fin_intersection:
        return 0.0

    nb_jours = (fin_intersection - debut_intersection).days + 1
    return taux_journalier * nb_jours


def extra_base_travaux_avant_activite(immobilisations: list[Immobilisation]) -> float:
    """Montant des travaux réalisés avant la première mise en location, à ajouter
    à la base amortissable du bâti plutôt qu'amortis séparément."""
    return sum(
        i.montant
        for i in immobilisations
        if i.avant_premiere_mise_en_location and i.type == NatureImmobilisation.travaux
    )


def dotation_building_component(
    component: BuildingComponent, property_: Property, extra_base_travaux: float, annee: int
) -> float:
    base_totale = property_.base_amortissable + extra_base_travaux
    base_composant = base_totale * (component.part_du_prix_pct / 100)
    return dotation_annuelle(
        base_composant, component.duree_amortissement, property_.date_debut_amortissement_bati, annee
    )


def montant_depasse_seuil_mobilier(montant_ttc: float, fiscal_params: FiscalParams) -> bool:
    """Seuil évalué avec le fichier fiscal de l'année d'achat (pas l'année courante)."""
    return montant_ttc >= fiscal_params.meuble_tourisme.amortissement.seuil_charge_directe_mobilier


def dotation_immobilisation(immobilisation: Immobilisation, annee: int) -> float:
    """0 pour les travaux intégrés à la base du bâti (avant première mise en
    location) — gérés via extra_base_travaux_avant_activite/dotation_building_component."""
    if immobilisation.avant_premiere_mise_en_location and immobilisation.type == NatureImmobilisation.travaux:
        return 0.0
    return dotation_annuelle(
        immobilisation.montant, immobilisation.duree_ans, immobilisation.date_mise_en_service, annee
    )
