"""Taux de change de référence de la BCE (API SDMX publique, gratuite, sans
clé) — nécessaire pour convertir en EUR les opérations libellées en devise
étrangère à leur date exacte (SPEC Phase 4). Ne lève jamais d'exception :
réseau indisponible, devise non cotée ou réponse inattendue -> None,
l'appelant exclut la ligne concernée avec un avertissement explicite plutôt
que de produire un montant silencieusement faux."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from functools import lru_cache

import httpx

ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{devise}.EUR.SP00.A"
FENETRE_JOURS = 7
TIMEOUT_SECONDS = 10.0


@lru_cache(maxsize=1024)
def fetch_rate(devise: str, jour: date) -> float | None:
    """Taux (devise par EUR) le plus récent connu à `jour` ou avant — gère les
    week-ends/jours fériés TARGET sans publication en élargissant la fenêtre
    de recherche en arrière. Un taux BCE publié ne change jamais rétroactivement,
    donc ce cache mémoire est sûr (contrairement à un cours boursier)."""
    if devise == "EUR":
        return 1.0

    debut = jour - timedelta(days=FENETRE_JOURS)
    try:
        response = httpx.get(
            ECB_URL.format(devise=devise),
            params={
                "startPeriod": debut.isoformat(),
                "endPeriod": jour.isoformat(),
                "format": "csvdata",
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        dernier_taux: float | None = None
        for row in reader:
            periode = date.fromisoformat(row["TIME_PERIOD"])
            if periode <= jour:
                dernier_taux = float(row["OBS_VALUE"])
        return dernier_taux
    except Exception:
        return None


def to_eur(montant: float, devise: str, jour: date) -> float | None:
    if devise == "EUR":
        return montant
    taux = fetch_rate(devise, jour)
    if taux is None:
        return None
    return montant / taux
