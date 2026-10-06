from datetime import date
from unittest.mock import patch

from sqlmodel import Session, select

from patrimoine import db
from patrimoine.models.enums import TypeTransaction
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.services.ibkr_credentials import IbkrCredentials
from patrimoine.services.market_data import PrixRecupere
from patrimoine.services.patrimoine_global import cash_disponible

REPORT_XML = """<FlexQueryResponse queryName="Test" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U1" fromDate="08/04/2026" toDate="10/02/2026" period="LastNCalendarDays" whenGenerated="10/04/2026;160357">
<OpenPositions>
<OpenPosition accountId="U1" conid="111" isin="LU1681045370" symbol="AEEM" position="10" costBasisPrice="6.5" currency="EUR" />
</OpenPositions>
<Trades>
</Trades>
<CashTransactions>
</CashTransactions>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>"""


def _creer_compte_ibkr(client) -> int:
    r = client.post(
        "/investissements",
        data={"nom": "CTO IBKR", "type_enveloppe": "cto", "courtier": "ibkr", "devise_base": "EUR"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return int(r.headers["location"].rstrip("/").split("/")[-1])


def test_solde_ouverture_cree_un_depot_compensatoire(client):
    account_id = _creer_compte_ibkr(client)

    with patch(
        "patrimoine.routes.investments.get_credentials",
        return_value=IbkrCredentials(token="tok", query_id="123"),
    ):
        with patch("patrimoine.services.ibkr_sync.ibkr_flex.fetch_report", return_value=REPORT_XML):
            r = client.post(f"/investissements/{account_id}/ibkr/solde-ouverture")

    assert r.status_code == 200
    assert "1 position(s) importée(s)" in r.text

    with Session(db.get_engine()) as s:
        transactions = s.exec(
            select(InvestmentTransaction).where(InvestmentTransaction.account_id == account_id)
        ).all()
        types = sorted(t.type for t in transactions)
        assert types == sorted([TypeTransaction.achat, TypeTransaction.depot])

        compte = s.get(InvestmentAccount, account_id)
        # Le solde d'ouverture n'est pas un découvert : le cash dérivé doit être
        # nul, pas négatif de la valeur de la position importée (régression cash négatif).
        assert cash_disponible(s, compte) == 0.0


def test_solde_ouverture_idempotent_pas_de_doublon(client):
    account_id = _creer_compte_ibkr(client)

    with patch(
        "patrimoine.routes.investments.get_credentials",
        return_value=IbkrCredentials(token="tok", query_id="123"),
    ):
        with patch("patrimoine.services.ibkr_sync.ibkr_flex.fetch_report", return_value=REPORT_XML):
            client.post(f"/investissements/{account_id}/ibkr/solde-ouverture")
            r2 = client.post(f"/investissements/{account_id}/ibkr/solde-ouverture")

    assert "0 position(s) importée(s)" in r2.text
    assert "1 déjà présente(s)" in r2.text


def test_solde_ouverture_backfill_depot_manquant_sur_import_pre_correctif(client):
    """Simule l'état bugué (achat sans dépôt compensatoire, comme les imports
    faits avant ce correctif) et vérifie qu'un reclic répare rétroactivement."""
    account_id = _creer_compte_ibkr(client)

    with Session(db.get_engine()) as s:
        s.add(
            InvestmentTransaction(
                account_id=account_id,
                date=date.today(),
                type=TypeTransaction.achat,
                quantite=10,
                prix_unitaire=6.5,
                devise="EUR",
                montant=65.0,
                description="Import IBKR — solde d'ouverture",
                external_id="ibkr-position-111",
            )
        )
        s.commit()

        compte = s.get(InvestmentAccount, account_id)
        assert cash_disponible(s, compte) == -65.0  # etat bugue, avant correctif

    with patch(
        "patrimoine.routes.investments.get_credentials",
        return_value=IbkrCredentials(token="tok", query_id="123"),
    ):
        with patch("patrimoine.services.ibkr_sync.ibkr_flex.fetch_report", return_value=REPORT_XML):
            r = client.post(f"/investissements/{account_id}/ibkr/solde-ouverture")

    assert "1 déjà présente(s)" in r.text
    # Jinja echappe l'apostrophe en &#39; dans le HTML rendu.
    assert "1 dépôt(s) d" in r.text
    assert "ouverture manquant(s) corrigé(s)" in r.text

    with Session(db.get_engine()) as s:
        compte = s.get(InvestmentAccount, account_id)
        assert cash_disponible(s, compte) == 0.0


def test_rafraichir_cours_depuis_la_fiche_compte_affiche_le_resume(client):
    account_id = _creer_compte_ibkr(client)

    with patch(
        "patrimoine.services.market_data.fetch_price",
        return_value=PrixRecupere(prix=10.0, devise="EUR"),
    ):
        r = client.post(f"/investissements/{account_id}/rafraichir-cours")

    assert r.status_code == 200
    assert "cours mis à jour" in r.text
