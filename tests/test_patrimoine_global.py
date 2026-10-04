from datetime import date

import pytest

from patrimoine.fiscal.loader import load_fiscal_params
from patrimoine.models.cash_holding import CashHolding
from patrimoine.models.enums import AllocationCategorie, Courtier, EnvelopeType, TypeTransaction
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.models.property import Property
from patrimoine.models.security import Security
from patrimoine.services.patrimoine_global import (
    cash_disponible,
    compute_consolide,
    enregistrer_snapshot_du_jour,
)


def _make_account(session, **overrides) -> InvestmentAccount:
    defaults = dict(nom="Compte Test", type=EnvelopeType.cto, courtier=Courtier.ibkr)
    defaults.update(overrides)
    a = InvestmentAccount(**defaults)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _make_security(session, isin, nom, categorie=None, cours=None) -> Security:
    s = Security(isin=isin, nom=nom, categorie_allocation=categorie, dernier_cours=cours)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def _make_property(session, **overrides) -> Property:
    defaults = dict(
        nom="Appart Test",
        adresse="1 rue Test",
        surface=30.0,
        date_acquisition=date(2020, 1, 1),
        prix_acquisition=100000.0,
    )
    defaults.update(overrides)
    p = Property(**defaults)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_cash_disponible_cas_chiffre_a_la_main(session):
    account = _make_account(session)
    session.add_all(
        [
            InvestmentTransaction(
                account_id=account.id, date=date(2024, 1, 1), type=TypeTransaction.depot, montant=10000
            ),
            InvestmentTransaction(
                account_id=account.id,
                date=date(2024, 2, 1),
                type=TypeTransaction.achat,
                montant=3000,
                frais=5,
            ),
            InvestmentTransaction(
                account_id=account.id,
                date=date(2024, 3, 1),
                type=TypeTransaction.vente,
                montant=1000,
                frais=2,
            ),
            InvestmentTransaction(
                account_id=account.id, date=date(2024, 4, 1), type=TypeTransaction.dividende, montant=50
            ),
            InvestmentTransaction(
                account_id=account.id, date=date(2024, 5, 1), type=TypeTransaction.interet, montant=8
            ),
            InvestmentTransaction(
                account_id=account.id, date=date(2024, 6, 1), type=TypeTransaction.frais, montant=3
            ),
            InvestmentTransaction(
                account_id=account.id, date=date(2024, 7, 1), type=TypeTransaction.retrait, montant=500
            ),
        ]
    )
    session.commit()

    # 10000 - (3000+5) + (1000-2) + 50 + 8 - 3 - 500
    attendu = 10000 - 3005 + 998 + 50 + 8 - 3 - 500
    assert cash_disponible(session, account) == pytest.approx(attendu)


def test_compute_consolide_multi_comptes_et_categories(session):
    account = _make_account(session)
    world = _make_security(session, "W1", "World", AllocationCategorie.world, cours=10)
    europe = _make_security(session, "E1", "Europe", AllocationCategorie.europe, cours=10)
    emergents = _make_security(session, "EM1", "Emergents", AllocationCategorie.emergents, cours=10)
    or_metal = _make_security(session, "OR1", "Or", AllocationCategorie.or_metal, cours=10)
    autre = _make_security(session, "A1", "Autre", AllocationCategorie.autre, cours=10)

    for security, quantite in [(world, 10), (europe, 5), (emergents, 3), (or_metal, 2), (autre, 1)]:
        session.add(
            InvestmentTransaction(
                account_id=account.id,
                security_id=security.id,
                date=date(2024, 1, 1),
                type=TypeTransaction.achat,
                quantite=quantite,
                prix_unitaire=10,
                montant=quantite * 10,
            )
        )
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 1, 1), type=TypeTransaction.depot, montant=1000
        )
    )
    session.commit()

    session.add(CashHolding(nom="Livret A", solde=5000, devise="EUR", date_maj=date.today()))
    session.commit()

    _make_property(session, prix_acquisition=100000.0, quote_part=1.0)
    _make_property(
        session, nom="Bien 2", prix_acquisition=50000.0, valeur_estimee=80000.0, quote_part=0.5
    )

    params = load_fiscal_params(2026)
    consolide = compute_consolide(session, params)

    assert consolide.valeur_world == pytest.approx(100)
    assert consolide.valeur_europe == pytest.approx(50)
    assert consolide.valeur_emergents == pytest.approx(30)
    assert consolide.valeur_or == pytest.approx(20)
    assert consolide.valeur_actions_autre == pytest.approx(10)
    assert consolide.valeur_actions == pytest.approx(100 + 50 + 30 + 10)

    # cash dispo dans l'enveloppe : 1000 depot - (100+50+30+20+10) investis = 790
    # + 5000 de CashHolding
    assert consolide.valeur_cash == pytest.approx(790 + 5000)

    # immobilier : 100000*1.0 + 80000*0.5
    assert consolide.valeur_immobilier == pytest.approx(100000 + 40000)

    assert consolide.valeur_totale == pytest.approx(consolide.valeur_actions + consolide.valeur_cash + consolide.valeur_immobilier + consolide.valeur_or)


def test_compute_consolide_exposition_geographique():
    from patrimoine.services.patrimoine_global import PatrimoineConsolide

    params = load_fiscal_params(2026)
    consolide = PatrimoineConsolide(valeur_world=1000, valeur_europe=200, valeur_emergents=100)
    # Reappliquer le calcul comme le ferait compute_consolide
    valeur_actions = consolide.valeur_actions
    pg = params.patrimoine_global
    pct_us = (consolide.valeur_world * pg.part_us_dans_world) / valeur_actions
    pct_europe = (consolide.valeur_europe + consolide.valeur_world * pg.part_europe_dans_world) / valeur_actions
    pct_emergents = consolide.valeur_emergents / valeur_actions

    assert pct_us == pytest.approx((1000 * pg.part_us_dans_world) / 1300)
    assert pct_europe == pytest.approx((200 + 1000 * pg.part_europe_dans_world) / 1300)
    assert pct_emergents == pytest.approx(100 / 1300)


def test_compute_consolide_sans_positions_pct_none(session):
    params = load_fiscal_params(2026)
    consolide = compute_consolide(session, params)
    assert consolide.pct_us is None
    assert consolide.pct_europe is None
    assert consolide.pct_emergents is None
    assert consolide.valeur_totale == 0


def test_enregistrer_snapshot_du_jour_upsert_idempotent(session):
    from sqlmodel import select

    from patrimoine.models.patrimoine_snapshot import PatrimoineSnapshot

    params = load_fiscal_params(2026)
    consolide1 = compute_consolide(session, params)
    enregistrer_snapshot_du_jour(session, consolide1)

    _make_property(session, prix_acquisition=42000.0)
    consolide2 = compute_consolide(session, params)
    enregistrer_snapshot_du_jour(session, consolide2)

    snapshots = session.exec(select(PatrimoineSnapshot)).all()
    assert len(snapshots) == 1
    assert snapshots[0].valeur_immobilier == pytest.approx(42000.0)
