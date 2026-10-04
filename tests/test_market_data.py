from unittest.mock import patch

import httpx

from patrimoine.services.market_data import fetch_price


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
