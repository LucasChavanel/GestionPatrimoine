from datetime import date

from patrimoine.fiscal.loader import load_fiscal_params
from patrimoine.models.enums import Courtier, EnvelopeType, TypeTransaction
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.services.pea import compute_suivi_pea, versements_cumules


def _make_account(session, **overrides) -> InvestmentAccount:
    defaults = dict(nom="PEA Test", type=EnvelopeType.pea, courtier=Courtier.trade_republic)
    defaults.update(overrides)
    a = InvestmentAccount(**defaults)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def test_versements_cumules_depot_moins_retrait(session):
    account = _make_account(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 1, 1), type=TypeTransaction.depot, montant=10000
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 6, 1), type=TypeTransaction.retrait, montant=2000
        )
    )
    session.commit()

    assert versements_cumules(session, account.id) == 8000


def test_versements_cumules_ignore_achats_ventes(session):
    account = _make_account(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 1, 1), type=TypeTransaction.depot, montant=10000
        )
    )
    session.add(
        InvestmentTransaction(
            account_id=account.id,
            date=date(2024, 2, 1),
            type=TypeTransaction.achat,
            quantite=10,
            prix_unitaire=100,
            montant=1000,
        )
    )
    session.commit()

    # La valorisation (via achat) ne doit jamais entrer dans le plafond de versements.
    assert versements_cumules(session, account.id) == 10000


def test_suivi_pea_marge_et_depassement(session):
    account = _make_account(session)
    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 1, 1), type=TypeTransaction.depot, montant=140000
        )
    )
    session.commit()

    params = load_fiscal_params(2026)
    suivi = compute_suivi_pea(session, account, params, aujourdhui=date(2024, 1, 1))
    assert suivi.versements_cumules == 140000
    assert suivi.plafond == params.pea.plafond_versements
    assert suivi.marge_disponible == params.pea.plafond_versements - 140000
    assert suivi.marge_disponible > 0

    session.add(
        InvestmentTransaction(
            account_id=account.id, date=date(2024, 2, 1), type=TypeTransaction.depot, montant=20000
        )
    )
    session.commit()
    suivi_depasse = compute_suivi_pea(session, account, params, aujourdhui=date(2024, 2, 1))
    assert suivi_depasse.marge_disponible < 0


def test_suivi_pea_anciennete_insuffisante(session):
    account = _make_account(session, date_ouverture=date(2023, 1, 1))
    params = load_fiscal_params(2026)
    suivi = compute_suivi_pea(session, account, params, aujourdhui=date(2024, 1, 1))
    assert suivi.anciennete_annees == (date(2024, 1, 1) - date(2023, 1, 1)).days / 365.25
    assert suivi.anciennete_suffisante is False


def test_suivi_pea_anciennete_suffisante(session):
    account = _make_account(session, date_ouverture=date(2015, 1, 1))
    params = load_fiscal_params(2026)
    suivi = compute_suivi_pea(session, account, params, aujourdhui=date(2024, 1, 1))
    assert suivi.anciennete_suffisante is True


def test_suivi_pea_sans_date_ouverture(session):
    account = _make_account(session, date_ouverture=None)
    params = load_fiscal_params(2026)
    suivi = compute_suivi_pea(session, account, params, aujourdhui=date(2024, 1, 1))
    assert suivi.anciennete_annees is None
    assert suivi.anciennete_suffisante is None
