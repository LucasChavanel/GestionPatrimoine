from datetime import date

import pytest

from patrimoine.models.enums import Courtier, EnvelopeType, TypeTransaction
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.models.security import Security
from patrimoine.services.positions import compute_positions


def _make_account(session, **overrides) -> InvestmentAccount:
    defaults = dict(nom="PEA Test", type=EnvelopeType.pea, courtier=Courtier.trade_republic)
    defaults.update(overrides)
    a = InvestmentAccount(**defaults)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _make_security(session, isin="FR0000000001", nom="Amundi MSCI World") -> Security:
    s = Security(isin=isin, nom=nom)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def test_prmp_achat_puis_vente_partielle(session):
    account = _make_account(session)
    security = _make_security(session)

    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, frais=5, montant=1000,
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 6, 1),
            type=TypeTransaction.vente, quantite=4, prix_unitaire=120, montant=480,
        )
    )
    session.commit()

    positions = compute_positions(session, account.id)
    assert len(positions) == 1
    p = positions[0]
    assert p.quantite_detenue == 6
    assert p.prmp == pytest.approx(100.5)
    assert p.montant_investi == pytest.approx(603.0)


def test_prmp_deux_achats_puis_vente(session):
    account = _make_account(session)
    security = _make_security(session)

    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000,
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 3, 1),
            type=TypeTransaction.achat, quantite=5, prix_unitaire=110, montant=550,
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 6, 1),
            type=TypeTransaction.vente, quantite=5, prix_unitaire=130, montant=650,
        )
    )
    session.commit()

    positions = compute_positions(session, account.id)
    assert len(positions) == 1
    p = positions[0]
    assert p.quantite_detenue == 10
    assert p.prmp == pytest.approx(1550 / 15)
    assert p.montant_investi == pytest.approx(10 * (1550 / 15))


def test_position_entierement_soldee_exclue(session):
    account = _make_account(session)
    security = _make_security(session)

    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000,
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=security.id, date=date(2024, 6, 1),
            type=TypeTransaction.vente, quantite=10, prix_unitaire=120, montant=1200,
        )
    )
    session.commit()

    positions = compute_positions(session, account.id)
    assert positions == []


def test_plusieurs_titres_sur_le_meme_compte(session):
    account = _make_account(session)
    world = _make_security(session, isin="FR0000000001", nom="World")
    europe = _make_security(session, isin="FR0000000002", nom="Europe")

    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=world.id, date=date(2024, 1, 1),
            type=TypeTransaction.achat, quantite=10, prix_unitaire=100, montant=1000,
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=europe.id, date=date(2024, 1, 1),
            type=TypeTransaction.achat, quantite=20, prix_unitaire=50, montant=1000,
        )
    )
    # Depot sans security_id : ne doit pas interferer avec le calcul des positions.
    session.add(
        InvestmentTransaction(
            account_id=account.id, security_id=None, date=date(2024, 1, 1),
            type=TypeTransaction.depot, montant=5000,
        )
    )
    session.commit()

    positions = compute_positions(session, account.id)
    assert len(positions) == 2
    isins = {p.security.isin for p in positions}
    assert isins == {"FR0000000001", "FR0000000002"}
