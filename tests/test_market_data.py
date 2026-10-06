from unittest.mock import patch

import httpx
from sqlmodel import Session

from patrimoine.models.security import Security
from patrimoine.services.market_data import fetch_price, refresh_all_prices


def _mock_response(json_data, status_code=200):
    request = httpx.Request("GET", "https://query1.finance.yahoo.com/v8/finance/chart/CW8.PA")
    return httpx.Response(status_code, json=json_data, request=request)


def test_fetch_price_succes():
    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 451.23, "currency": "EUR"}}]}}
    with patch("patrimoine.services.market_data.httpx.get", return_value=_mock_response(payload)):
        prix = fetch_price("CW8.PA")
    assert prix is not None
    assert prix.prix == 451.23
    assert prix.devise == "EUR"


def test_fetch_price_erreur_reseau_retourne_none():
    with patch("patrimoine.services.market_data.httpx.get", side_effect=httpx.ConnectError("offline")):
        prix = fetch_price("CW8.PA")
    assert prix is None


def test_fetch_price_reponse_http_erreur_retourne_none():
    with patch(
        "patrimoine.services.market_data.httpx.get",
        return_value=_mock_response({"error": "not found"}, status_code=404),
    ):
        prix = fetch_price("TICKER_INVALIDE")
    assert prix is None


def test_fetch_price_json_inattendu_retourne_none():
    with patch("patrimoine.services.market_data.httpx.get", return_value=_mock_response({"chart": {}})):
        prix = fetch_price("CW8.PA")
    assert prix is None


def test_refresh_all_prices_met_a_jour_classe_sans_ticker_et_echecs(session: Session):
    avec_ticker_ok = Security(isin="FR001", nom="World", ticker_yahoo="CW8.PA")
    avec_ticker_echec = Security(isin="FR002", nom="Invalide", ticker_yahoo="INVALIDE")
    sans_ticker = Security(isin="FR003", nom="Sans ticker")
    session.add_all([avec_ticker_ok, avec_ticker_echec, sans_ticker])
    session.commit()

    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 451.23, "currency": "EUR"}}]}}

    def fake_get(url, **kwargs):
        if "CW8.PA" in url:
            return _mock_response(payload)
        return _mock_response({"error": "not found"}, status_code=404)

    with patch("patrimoine.services.market_data.httpx.get", side_effect=fake_get):
        resultat = refresh_all_prices(session)

    assert resultat.mis_a_jour == 1
    assert resultat.echecs == 1
    assert resultat.sans_ticker == 1
    session.refresh(avec_ticker_ok)
    assert avec_ticker_ok.dernier_cours == 451.23
