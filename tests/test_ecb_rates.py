from datetime import date
from unittest.mock import patch

import httpx

from patrimoine.services.ecb_rates import fetch_rate, to_eur

CSV_AVEC_OBSERVATIONS = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-09-25,1.1403
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-09-28,1.1378
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-09-29,1.1355
"""

CSV_VIDE = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"


def _response(text, status_code=200):
    request = httpx.Request("GET", "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A")
    return httpx.Response(status_code, text=text, request=request)


def test_fetch_rate_jour_exact():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get", return_value=_response(CSV_AVEC_OBSERVATIONS)):
        taux = fetch_rate("USD", date(2026, 9, 29))
    assert taux == 1.1355


def test_fetch_rate_weekend_retombe_sur_dernier_jour_ouvre():
    fetch_rate.cache_clear()
    # Dimanche 27/09 : pas d'observation ce jour-la dans le CSV, doit prendre le 25/09.
    with patch("patrimoine.services.ecb_rates.httpx.get", return_value=_response(CSV_AVEC_OBSERVATIONS)):
        taux = fetch_rate("USD", date(2026, 9, 27))
    assert taux == 1.1403


def test_fetch_rate_eur_jamais_appel_reseau():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get") as mock_get:
        taux = fetch_rate("EUR", date(2026, 9, 29))
    assert taux == 1.0
    mock_get.assert_not_called()


def test_fetch_rate_erreur_reseau_retourne_none():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get", side_effect=httpx.ConnectError("offline")):
        taux = fetch_rate("USD", date(2026, 9, 30))
    assert taux is None


def test_fetch_rate_aucune_observation_retourne_none():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get", return_value=_response(CSV_VIDE)):
        taux = fetch_rate("USD", date(2026, 10, 1))
    assert taux is None


def test_to_eur_conversion():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get", return_value=_response(CSV_AVEC_OBSERVATIONS)):
        montant_eur = to_eur(113.55, "USD", date(2026, 9, 29))
    assert montant_eur == 100.0


def test_to_eur_sans_devise_etrangere_pas_de_conversion():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get") as mock_get:
        montant_eur = to_eur(100.0, "EUR", date(2026, 9, 29))
    assert montant_eur == 100.0
    mock_get.assert_not_called()


def test_to_eur_taux_indisponible_retourne_none():
    fetch_rate.cache_clear()
    with patch("patrimoine.services.ecb_rates.httpx.get", side_effect=httpx.ConnectError("offline")):
        montant_eur = to_eur(100.0, "USD", date(2026, 10, 2))
    assert montant_eur is None
