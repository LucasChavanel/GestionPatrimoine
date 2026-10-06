from datetime import date

from sqlmodel import Session, select

from patrimoine import db
from patrimoine.models.cash_holding import CashHolding


def test_creer_compte_courant_sans_details_terme(client):
    r = client.post(
        "/liquidites",
        data={"nom": "Compte courant", "solde": "1500.50", "devise": "EUR"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get("/liquidites")
    assert r.status_code == 200
    assert "Compte courant" in r.text
    assert "1 500.50" in r.text


def test_creer_compte_a_terme_avec_details(client):
    r = client.post(
        "/liquidites",
        data={
            "nom": "CAT BoursoBank",
            "solde": "10000",
            "devise": "EUR",
            "taux_pct": "3.5",
            "duree_mois": "12",
            "date_fin": "2027-01-15",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    with Session(db.get_engine()) as s:
        holding = s.exec(select(CashHolding).where(CashHolding.nom == "CAT BoursoBank")).first()
        assert holding is not None
        assert holding.taux_pct == 3.5
        assert holding.duree_mois == 12
        assert holding.date_fin == date(2027, 1, 15)

    page = client.get("/liquidites")
    assert "3.5" in page.text
    assert "12 mois" in page.text
    assert "2027-01-15" in page.text


def test_modifier_conserve_et_met_a_jour_les_champs_terme(client):
    r = client.post(
        "/liquidites",
        data={"nom": "Livret A", "solde": "5000", "devise": "EUR"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    with Session(db.get_engine()) as s:
        holding = s.exec(select(CashHolding).where(CashHolding.nom == "Livret A")).first()
        assert holding.taux_pct is None
        holding_id = holding.id

    r = client.post(
        f"/liquidites/{holding_id}",
        data={
            "nom": "Livret A",
            "solde": "5200",
            "devise": "EUR",
            "taux_pct": "3",
            "duree_mois": "",
            "date_fin": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    with Session(db.get_engine()) as s:
        holding_maj = s.get(CashHolding, holding_id)
        assert holding_maj.solde == 5200
        assert holding_maj.taux_pct == 3.0
        assert holding_maj.duree_mois is None
        assert holding_maj.date_fin is None


def test_supprimer(client):
    client.post(
        "/liquidites", data={"nom": "A supprimer", "solde": "100", "devise": "EUR"}, follow_redirects=False
    )
    with Session(db.get_engine()) as s:
        holding_id = s.exec(select(CashHolding).where(CashHolding.nom == "A supprimer")).first().id

    r = client.post(f"/liquidites/{holding_id}/supprimer", follow_redirects=False)
    assert r.status_code == 303

    with Session(db.get_engine()) as s:
        assert s.get(CashHolding, holding_id) is None
