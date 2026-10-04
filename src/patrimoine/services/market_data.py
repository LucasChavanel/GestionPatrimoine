"""Récupération du dernier cours via l'endpoint public (non officiel) de Yahoo
Finance. Ne lève jamais d'exception : réseau indisponible, ticker invalide ou
réponse inattendue retournent `None`, l'appelant garde le dernier cours connu
en base — l'app reste utilisable hors ligne."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
USER_AGENT = "Mozilla/5.0 (compatible; Patrimoine/1.0; usage personnel)"
TIMEOUT_SECONDS = 5.0


@dataclass
class PrixRecupere:
    prix: float
    devise: str


def fetch_price(ticker_yahoo: str) -> PrixRecupere | None:
    try:
        response = httpx.get(
            YAHOO_CHART_URL.format(ticker=ticker_yahoo),
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        prix = meta["regularMarketPrice"]
        devise = meta["currency"]
        if prix is None or devise is None:
            return None
        return PrixRecupere(prix=float(prix), devise=str(devise))
    except Exception:
        return None
