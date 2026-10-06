import re
from unittest.mock import patch

from patrimoine.services.market_data import PrixRecupere


def _dernier_security_id(client) -> str:
    r_liste = client.get("/titres")
    ids = re.findall(r"/titres/(\d+)/modifier", r_liste.text)
    return ids[-1]


def test_rafraichir_cours_sans_ticker_affiche_message_explicite(client):
    client.post("/titres", data={"isin": "FR1", "nom": "Sans ticker"}, follow_redirects=False)
    security_id = _dernier_security_id(client)

    r = client.post(f"/titres/{security_id}/rafraichir-cours")
    assert r.status_code == 200
    assert "aucun ticker Yahoo renseigné" in r.text


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
    client.post("/titres", data={"isin": "FR4", "nom": "World", "ticker_yahoo": "CW8.PA"}, follow_redirects=False)
    client.post("/titres", data={"isin": "FR5", "nom": "Sans ticker"}, follow_redirects=False)

    with patch(
        "patrimoine.services.market_data.fetch_price",
        return_value=PrixRecupere(prix=10.0, devise="EUR"),
    ):
        r = client.post("/titres/rafraichir-tout")
    assert r.status_code == 200
    assert "1 cours mis à jour, 0 échec(s)" in r.text
    assert "1 titre(s) sans ticker Yahoo renseigné" in r.text
