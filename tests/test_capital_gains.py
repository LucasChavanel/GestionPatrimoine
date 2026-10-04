from datetime import date
from unittest.mock import patch

import pytest

from patrimoine.models.enums import Courtier, EnvelopeType, TypeTransaction
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.models.security import Security
from patrimoine.services.capital_gains import compute_dividendes_cto, compute_plus_values_cto


def _make_account(session, **overrides) -> InvestmentAccount:
    defaults = dict(nom="CTO Test", type=EnvelopeType.cto, courtier=Courtier.ibkr)
    defaults.update(overrides)
    a = InvestmentAccount(**defaults)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _make_security(session, isin="FR0000000001", nom="Titre Test") -> Security:
    s = Security(isin=isin, nom=nom)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def test_plus_value_eur_achat_puis_vente(session):
    account = _make_account(session)
    security = _make_security(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, frais=5, montant=1000, devise="EUR",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 6, 1),
            type=TypeTransaction.vente, quantite=4, prix_unitaire=150, frais=2, montant=600, devise="EUR",
        )
    )
    session.commit()

    # PRMP = (10*100+5)/10 = 100.5 ; cout cede = 4*100.5 = 402 ; produit = 600-2 = 598
    # plus-value = 598 - 402 = 196
    resultat = compute_plus_values_cto(session, 2026)
    assert resultat.plus_value_annee == pytest.approx(196.0)
    assert resultat.avertissements == []


def test_plus_value_ignoree_hors_annee(session):
    account = _make_account(session)
    security = _make_security(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2025, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000, devise="EUR",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2025, 6, 1),
            type=TypeTransaction.vente, quantite=10, prix_unitaire=150, montant=1500, devise="EUR",
        )
    )
    session.commit()

    resultat = compute_plus_values_cto(session, 2026)
    assert resultat.plus_value_annee == 0.0


def test_plus_value_pea_exclu(session):
    account = _make_account(session, type=EnvelopeType.pea, courtier=Courtier.trade_republic)
    security = _make_security(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000, devise="EUR",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 6, 1),
            type=TypeTransaction.vente, quantite=10, prix_unitaire=150, montant=1500, devise="EUR",
        )
    )
    session.commit()

    resultat = compute_plus_values_cto(session, 2026)
    assert resultat.plus_value_annee == 0.0


def test_plus_value_devise_etrangere_convertie(session):
    account = _make_account(session)
    security = _make_security(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000, devise="USD",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 6, 1),
            type=TypeTransaction.vente, quantite=10, prix_unitaire=150, montant=1500, devise="USD",
        )
    )
    session.commit()

    # Taux fixe 1 USD = 0.5 EUR (to_eur retourne montant_natif/taux habituellement,
    # ici on simplifie en mockant to_eur directement).
    def fake_to_eur(montant, devise, jour):
        return montant * 0.5 if devise != "EUR" else montant

    with patch("patrimoine.services.capital_gains.to_eur", side_effect=fake_to_eur):
        resultat = compute_plus_values_cto(session, 2026)

    # cout EUR = 1000*0.5 = 500 ; produit EUR = 1500*0.5 = 750 ; plus-value = 250
    assert resultat.plus_value_annee == pytest.approx(250.0)
    assert resultat.avertissements == []


def test_plus_value_conversion_echouee_exclue_avec_avertissement(session):
    account = _make_account(session)
    security = _make_security(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2026, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000, devise="USD",
        )
    )
    session.commit()

    with patch("patrimoine.services.capital_gains.to_eur", return_value=None):
        resultat = compute_plus_values_cto(session, 2026)

    assert resultat.plus_value_annee == 0.0
    assert len(resultat.avertissements) == 1
    assert "BCE" in resultat.avertissements[0]


def test_dividendes_et_retenues_cto(session):
    account = _make_account(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2026, 3, 1), type=TypeTransaction.dividende,
            montant=100, devise="EUR",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2026, 3, 1), type=TypeTransaction.retenue_source,
            montant=15, devise="EUR",
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2025, 3, 1), type=TypeTransaction.dividende,
            montant=999, devise="EUR",
        )
    )
    session.commit()

    resultat = compute_dividendes_cto(session, 2026)
    assert resultat.dividendes_bruts == 100.0
    assert resultat.retenues_source == 15.0


def test_dividendes_pea_exclus(session):
    account = _make_account(session, type=EnvelopeType.pea, courtier=Courtier.trade_republic)
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2026, 3, 1), type=TypeTransaction.dividende,
            montant=100, devise="EUR",
        )
    )
    session.commit()

    resultat = compute_dividendes_cto(session, 2026)
    assert resultat.dividendes_bruts == 0.0
