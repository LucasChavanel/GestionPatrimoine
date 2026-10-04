"""Allocation cible World/Europe (80/20) sur un compte PEA : valorise les
positions calculées (voir services/positions.py) au dernier cours connu de
chaque titre, et vérifie que la part Europe reste dans la bande de
rééquilibrage (ex. 15-25 %) définie en paramètres fiscaux."""

from __future__ import annotations

from dataclasses import dataclass

from ..fiscal.loader import FiscalParams
from ..models.enums import AllocationCategorie
from .positions import PositionCalculee


@dataclass
class AllocationCalculee:
    valeur_world: float
    valeur_europe: float
    valeur_autre: float
    valeur_totale: float
    pct_europe: float | None
    hors_bande: bool | None


def _valeur_position(position: PositionCalculee) -> float:
    cours = position.security.dernier_cours
    if cours is None:
        return position.montant_investi
    return position.quantite_detenue * cours


def compute_allocation(positions: list[PositionCalculee], params: FiscalParams) -> AllocationCalculee:
    valeur_world = 0.0
    valeur_europe = 0.0
    valeur_autre = 0.0
    for position in positions:
        valeur = _valeur_position(position)
        categorie = position.security.categorie_allocation
        if categorie == AllocationCategorie.world:
            valeur_world += valeur
        elif categorie == AllocationCategorie.europe:
            valeur_europe += valeur
        else:
            valeur_autre += valeur

    valeur_totale = valeur_world + valeur_europe + valeur_autre
    valeur_allouee = valeur_world + valeur_europe
    pct_europe = valeur_europe / valeur_allouee if valeur_allouee > 0 else None

    hors_bande: bool | None = None
    if pct_europe is not None and params.pea is not None:
        hors_bande = not (
            params.pea.allocation_europe_bande_min_pct
            <= pct_europe
            <= params.pea.allocation_europe_bande_max_pct
        )

    return AllocationCalculee(
        valeur_world=valeur_world,
        valeur_europe=valeur_europe,
        valeur_autre=valeur_autre,
        valeur_totale=valeur_totale,
        pct_europe=pct_europe,
        hors_bande=hors_bande,
    )
