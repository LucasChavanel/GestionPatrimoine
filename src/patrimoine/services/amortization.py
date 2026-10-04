"""Moteur d'amortissement linéaire au prorata en jours.

Décisions prises avec l'utilisateur (voir conversation / plan) :
- Prorata en jours sur toute la durée de vie de l'actif (1er ET dernier exercice
  proratisés), taux journalier = base / (durée_ans × 365).
- Les travaux d'amélioration/construction réalisés avant la première mise en
  location s'intègrent à la base amortissable du bâti (répartis sur les
  BuildingComponent), plutôt que d'être amortis séparément.
- Le mobilier sous le seuil (fichier fiscal de l'année d'achat) est une charge
  directe, pas un amortissement.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..fiscal.loader import FiscalParams
from ..models.enums import NatureWorks
from ..models.furniture import Furniture
from ..models.property import BuildingComponent, Property
from ..models.works import Works

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


def extra_base_travaux_avant_activite(works_list: list[Works]) -> float:
    """Montant des travaux d'amélioration/construction réalisés avant la première
    mise en location, à ajouter à la base amortissable du bâti."""
    return sum(
        w.montant_ttc
        for w in works_list
        if w.avant_premiere_mise_en_location
        and w.nature in (NatureWorks.amelioration, NatureWorks.construction_agrandissement)
    )


def dotation_building_component(
    component: BuildingComponent, property_: Property, extra_base_travaux: float, annee: int
) -> float:
    base_totale = property_.base_amortissable + extra_base_travaux
    base_composant = base_totale * (component.part_du_prix_pct / 100)
    return dotation_annuelle(
        base_composant, component.duree_amortissement, property_.date_debut_amortissement_bati, annee
    )


def dotation_works(works: Works, annee: int) -> float:
    """0 si entretien/réparation (charge directe, gérée dans le simulateur) ou si
    avant première mise en location (intégré à la base du bâti, voir ci-dessus)."""
    if works.avant_premiere_mise_en_location or not works.est_amortissable:
        return 0.0
    if not works.duree_amortissement:
        return 0.0
    return dotation_annuelle(works.montant_ttc, works.duree_amortissement, works.date, annee)


def is_furniture_charge_directe(furniture: Furniture, fiscal_params: FiscalParams) -> bool:
    """Seuil évalué avec le fichier fiscal de l'année d'achat (pas l'année courante)."""
    return furniture.montant_ttc < fiscal_params.meuble_tourisme.amortissement.seuil_charge_directe_mobilier


def dotation_furniture(furniture: Furniture, annee: int, fiscal_params_achat: FiscalParams) -> float:
    if is_furniture_charge_directe(furniture, fiscal_params_achat):
        return 0.0
    return dotation_annuelle(furniture.montant_ttc, furniture.duree_amortissement, furniture.date_achat, annee)
