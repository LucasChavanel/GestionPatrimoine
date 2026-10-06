"""Récupération du dernier cours et résolution ISIN → ticker via l'endpoint
public (non officiel) de Yahoo Finance. Ne lève jamais d'exception : réseau
indisponible, ticker/ISIN invalide ou réponse inattendue retournent `None`,
l'appelant garde le dernier cours connu en base — l'app reste utilisable hors
ligne."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
from sqlmodel import Session, select

from ..models.security import Security

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
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


def resolve_ticker_from_isin(isin: str) -> str | None:
    """Trouve le ticker Yahoo Finance correspondant à un ISIN via l'endpoint de
    recherche Yahoo — permet de renseigner automatiquement `ticker_yahoo` sans
    saisie manuelle. Retourne `None` si rien de fiable n'est trouvé."""
    if not isin:
        return None
    try:
        response = httpx.get(
            YAHOO_SEARCH_URL,
            params={"q": isin, "quotesCount": 5, "newsCount": 0},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        for quote in data.get("quotes", []):
            symbol = quote.get("symbol")
            if quote.get("isYahooFinance") and symbol:
                return str(symbol)
        return None
    except Exception:
        return None


@dataclass
class RafraichissementResultat:
    mis_a_jour: int = 0
    echecs: int = 0
    sans_ticker: int = 0
    tickers_resolus: int = 0


def refresh_all_prices(session: Session) -> RafraichissementResultat:
    """Rafraîchit tous les titres — résout automatiquement le ticker Yahoo
    manquant à partir de l'ISIN, puis récupère le cours. Utilisé par les
    boutons manuels ET par le rafraîchissement automatique au lancement
    (voir main.py::run), toujours la même logique, jamais dupliquée."""
    resultat = RafraichissementResultat()
    securities = session.exec(select(Security)).all()
    for security in securities:
        if not security.ticker_yahoo:
            ticker = resolve_ticker_from_isin(security.isin)
            if ticker:
                security.ticker_yahoo = ticker
                resultat.tickers_resolus += 1
            else:
                resultat.sans_ticker += 1
                continue
        prix = fetch_price(security.ticker_yahoo)
        if prix is None:
            resultat.echecs += 1
            continue
        security.dernier_cours = prix.prix
        security.dernier_cours_devise = prix.devise
        security.dernier_cours_date = date.today()
        session.add(security)
        resultat.mis_a_jour += 1
    session.commit()
    return resultat
