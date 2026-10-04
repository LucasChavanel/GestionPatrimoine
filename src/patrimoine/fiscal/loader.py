"""Chargement des paramètres fiscaux versionnés (fiscal/params/<année>.yaml).

Les règles fiscales sont des paramètres, jamais du code en dur (SPEC §1).
Chaque bloc a un champ `verified`, que l'utilisateur passe à `true` après vérification ;
`unverified_warnings()` permet d'afficher un avertissement tant que ce n'est pas fait.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

PARAMS_DIR = Path(__file__).resolve().parent / "params"


class MicroBicBareme(BaseModel):
    abattement: float
    plafond_recettes: float
    source: str
    verified: bool = False


class MicroBic(BaseModel):
    non_classe: MicroBicBareme
    classe: MicroBicBareme


class DureesDefaut(BaseModel):
    gros_oeuvre: int
    facade_etancheite: int
    installations_techniques: int
    agencements: int
    mobilier: int


class Amortissement(BaseModel):
    seuil_charge_directe_mobilier: float
    durees_defaut: DureesDefaut
    source: str
    verified: bool = False


class MeubleTourisme(BaseModel):
    micro_bic: MicroBic
    amortissement: Amortissement


class PrelevementsSociaux(BaseModel):
    revenus_bic_lmnp: float
    revenus_capital_mobilier: float
    revenus_fonciers: float
    verified: bool = False


class TraitementCategorieCharge(BaseModel):
    """Traitement d'une catégorie de charge par régime :
    deductible / non_deductible / immobilisation / immobilisation_si_seuil /
    non_applicable / a_qualifier."""

    lmnp_reel: str
    foncier_reel: str


class MicroFoncierBareme(BaseModel):
    abattement: float
    plafond_recettes: float
    source: str
    verified: bool = False


class FoncierReelParams(BaseModel):
    frais_gestion_forfaitaire_par_lot: float
    plafond_deficit_imputable_revenu_global: float
    source: str
    verified: bool = False


class Foncier(BaseModel):
    micro_foncier: MicroFoncierBareme
    reel: FoncierReelParams


class Pea(BaseModel):
    plafond_versements: float
    anciennete_minimale_annees: int
    allocation_europe_bande_min_pct: float
    allocation_europe_bande_max_pct: float
    source: str
    verified: bool = False


class PatrimoineGlobalParams(BaseModel):
    part_us_dans_world: float
    part_europe_dans_world: float
    source: str
    verified: bool = False


class FiscalParams(BaseModel):
    year: int
    meuble_tourisme: MeubleTourisme
    foncier: Foncier
    prelevements_sociaux: PrelevementsSociaux
    categories_charges: dict[str, TraitementCategorieCharge] = {}
    cases_declaration: dict = {}
    pea: Pea | None = None
    patrimoine_global: PatrimoineGlobalParams | None = None

    def _avertissement_prelevements_sociaux(self) -> list[str]:
        if self.prelevements_sociaux.verified:
            return []
        return [f"Prélèvements sociaux {self.year} : taux non vérifiés"]

    def unverified_warnings_lmnp(self) -> list[str]:
        """Avertissements pertinents pour un bien meublé (micro-BIC/réel LMNP)."""
        warnings: list[str] = []
        mb = self.meuble_tourisme.micro_bic
        if not mb.non_classe.verified:
            warnings.append(
                f"Micro-BIC non classé {self.year} : paramètres non vérifiés ({mb.non_classe.source})"
            )
        if not mb.classe.verified:
            warnings.append(
                f"Micro-BIC classé {self.year} : paramètres non vérifiés ({mb.classe.source})"
            )
        am = self.meuble_tourisme.amortissement
        if not am.verified:
            warnings.append(f"Amortissement {self.year} : durées/seuil non vérifiés ({am.source})")
        warnings.extend(self._avertissement_prelevements_sociaux())
        return warnings

    def unverified_warnings_foncier(self) -> list[str]:
        """Avertissements pertinents pour un bien nu (micro-foncier/réel)."""
        warnings: list[str] = []
        if not self.foncier.micro_foncier.verified:
            warnings.append(
                f"Micro-foncier {self.year} : paramètres non vérifiés ({self.foncier.micro_foncier.source})"
            )
        if not self.foncier.reel.verified:
            warnings.append(
                f"Foncier réel {self.year} : paramètres non vérifiés ({self.foncier.reel.source})"
            )
        warnings.extend(self._avertissement_prelevements_sociaux())
        return warnings

    def unverified_warnings_pea(self) -> list[str]:
        """Avertissements pertinents pour un compte PEA (plafond, bande d'allocation)."""
        if self.pea is None or self.pea.verified:
            return []
        return [f"PEA {self.year} : paramètres non vérifiés ({self.pea.source})"]

    def unverified_warnings_patrimoine_global(self) -> list[str]:
        """Avertissements pertinents pour le dashboard consolidé (exposition géo)."""
        if self.patrimoine_global is None or self.patrimoine_global.verified:
            return []
        return [f"Patrimoine global {self.year} : paramètres non vérifiés ({self.patrimoine_global.source})"]

    def unverified_warnings(self) -> list[str]:
        """Vue d'ensemble (dashboard) : tous les avertissements, toutes familles
        confondues — pas de notion de bien précis à ce niveau."""
        warnings = self.unverified_warnings_lmnp()
        for w in self.unverified_warnings_foncier():
            if w not in warnings:
                warnings.append(w)
        for w in self.unverified_warnings_pea():
            if w not in warnings:
                warnings.append(w)
        for w in self.unverified_warnings_patrimoine_global():
            if w not in warnings:
                warnings.append(w)
        return warnings


@lru_cache
def load_fiscal_params(year: int) -> FiscalParams:
    path = PARAMS_DIR / f"{year}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in PARAMS_DIR.glob("*.yaml"))
        if not available:
            raise FileNotFoundError("Aucun fichier de paramètres fiscaux trouvé dans fiscal/params/")
        path = PARAMS_DIR / f"{available[-1]}.yaml"
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return FiscalParams.model_validate(data)
