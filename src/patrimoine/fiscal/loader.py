"""Chargement des paramètres fiscaux versionnés (fiscal/params/<année>.yaml).

Les règles fiscales sont des paramètres, jamais du code en dur (SPEC §1).
Chaque bloc a un champ `verified`, que l'utilisateur passe à `true` après vérification ;
`unverified_warnings()` permet d'afficher un avertissement tant que ce n'est pas fait.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

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
    verified: bool = False


class FiscalParams(BaseModel):
    year: int
    meuble_tourisme: MeubleTourisme
    prelevements_sociaux: PrelevementsSociaux
    cases_declaration: Dict = {}

    def unverified_warnings(self) -> List[str]:
        warnings: List[str] = []
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
        if not self.prelevements_sociaux.verified:
            warnings.append(f"Prélèvements sociaux {self.year} : taux non vérifiés")
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
