import re
from unittest.mock import patch

from patrimoine.services.market_data import PrixRecupere


def _dernier_security_id(client) -> str:
    r_liste = client.get("/titres")
    ids = re.findall(r"/titres/(\d+)/modifier", r_liste.text)
    return ids[-1]


def test_rafraichir_cours_sans_ticker_affiche_message_explicite(client):
    with patch("patrimoine.routes.securities.resolve_ticker_from_isin", return_value=None):
        client.post("/titres", data={"isin": "FR1", "nom": "Sans ticker"}, follow_redirects=False)
        security_id = _dernier_security_id(client)

        r = client.post(f"/titres/{security_id}/rafraichir-cours")
    assert r.status_code == 200
    assert "aucun ticker Yahoo trouvé automatiquement" in r.text


def test_rafraichir_cours_sans_ticker_resout_automatiquement_depuis_isin(client):
    with patch("patrimoine.routes.securities.resolve_ticker_from_isin", return_value=None):
        client.post("/titres", data={"isin": "FR1B", "nom": "World auto"}, follow_redirects=False)
    security_id = _dernier_security_id(client)

    with (
        patch("patrimoine.routes.securities.resolve_ticker_from_isin", return_value="CW8.PA"),
        patch(
            "patrimoine.routes.securities.fetch_price",
            return_value=PrixRecupere(prix=451.23, devise="EUR"),
        ),
    ):
        r = client.post(f"/titres/{security_id}/rafraichir-cours")
    assert r.status_code == 200
    assert "cours mis à jour (451.23 EUR)" in r.text


def test_rafraichir_cours_succes_affiche_le_nouveau_cours(client):
    client.post(
        "/titres", data={"isin": "FR2", "nom": "World", "ticker_yahoo": "CW8.PA"}, follow_redirects=False
    )
    security_id = _dernier_security_id(client)

    with patch(
        "patrimoine.routes.securities.fetch_price",
        return_value=PrixRecupere(prix=451.23, devise="EUR"),
    ):
        r = client.post(f"/titres/{security_id}/rafraichir-cours")
    assert r.status_code == 200
    assert "cours mis à jour (451.23 EUR)" in r.text


def test_rafraichir_cours_echec_reseau_affiche_message_explicite(client):
    client.post(
        "/titres", data={"isin": "FR3", "nom": "World", "ticker_yahoo": "CW8.PA"}, follow_redirects=False
    )
    security_id = _dernier_security_id(client)

    with patch("patrimoine.routes.securities.fetch_price", return_value=None):
        r = client.post(f"/titres/{security_id}/rafraichir-cours")
    assert r.status_code == 200
    assert "échec de la récupération du cours" in r.text


def test_rafraichir_tout_resume_les_resultats(client):
    with patch("patrimoine.routes.securities.resolve_ticker_from_isin", return_value=None):
        client.post(
            "/titres", data={"isin": "FR4", "nom": "World", "ticker_yahoo": "CW8.PA"}, follow_redirects=False
        )
        client.post("/titres", data={"isin": "FR5", "nom": "Sans ticker"}, follow_redirects=False)

    with (
        patch("patrimoine.services.market_data.fetch_price", return_value=PrixRecupere(prix=10.0, devise="EUR")),
        patch("patrimoine.services.market_data.resolve_ticker_from_isin", return_value=None),
    ):
        r = client.post("/titres/rafraichir-tout")
    assert r.status_code == 200
    assert "1 cours mis à jour, 0 échec(s)" in r.text
    assert "1 titre(s) sans ticker Yahoo trouvé" in r.text


def test_rafraichir_tout_resout_automatiquement_les_tickers_manquants(client):
    with patch("patrimoine.routes.securities.resolve_ticker_from_isin", return_value=None):
        client.post("/titres", data={"isin": "FR6", "nom": "World auto"}, follow_redirects=False)

    with (
        patch("patrimoine.services.market_data.resolve_ticker_from_isin", return_value="CW8.PA"),
        patch("patrimoine.services.market_data.fetch_price", return_value=PrixRecupere(prix=10.0, devise="EUR")),
    ):
        r = client.post("/titres/rafraichir-tout")
    assert r.status_code == 200
    assert "1 cours mis à jour, 0 échec(s)" in r.text
    # Jinja echappe l'apostrophe en &#39; dans le HTML rendu.
    assert "1 ticker(s) Yahoo résolu(s) automatiquement depuis l" in r.text
    assert "ISIN" in r.text
