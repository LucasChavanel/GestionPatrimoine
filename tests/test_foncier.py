from datetime import date

import pytest

from patrimoine.models.booking import Booking
from patrimoine.models.enums import Plateforme, StatutBooking, TypeLocation
from patrimoine.models.expense import Expense
from patrimoine.models.property import Property
from patrimoine.services.foncier import simulate_foncier_year


def _make_property(session, **overrides) -> Property:
    defaults = dict(
        nom="Nu Test",
        adresse="x",
        surface=40,
        date_acquisition=date(2026, 1, 1),
        prix_acquisition=150_000,
        type_location=TypeLocation.nu,
        date_premiere_mise_en_location=date(2026, 1, 1),
    )
    defaults.update(overrides)
    p = Property(**defaults)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _loyer(property_id, montant_brut, annee, mois=6, date_paiement=None):
    if date_paiement is None:
        date_paiement = date(annee, mois, 1)
    return Booking(
        property_id=property_id,
        date_arrivee=date(annee, mois, 1),
        date_depart=date(annee, mois + 1, 1) if mois < 12 else date(annee, 12, 31),
        plateforme=Plateforme.direct,
        montant_brut=montant_brut,
        statut=StatutBooking.confirmee,
        date_paiement=date_paiement,
    )


def test_micro_foncier_applicable_et_abattement(session):
    p = _make_property(session)
    session.add(_loyer(p.id, 10_000, 2026))
    session.commit()

    result = simulate_foncier_year(session, p, 2026, tmi=0.30)

    assert result.recettes == 10_000
    assert result.micro_foncier.applicable is True
    assert result.micro_foncier.revenu_imposable == 7_000  # 10000 * (1 - 0.30)


def test_micro_foncier_non_applicable_si_plafond_depasse(session):
    p = _make_property(session)
    session.add(_loyer(p.id, 20_000, 2026))  # > plafond 15000
    session.commit()

    result = simulate_foncier_year(session, p, 2026, tmi=0.30)

    assert result.micro_foncier.applicable is False
    assert any("non applicable" in a for a in result.avertissements)


def test_forfait_gestion_applique_meme_sans_charge(session):
    p = _make_property(session)
    session.add(_loyer(p.id, 5_000, 2026))
    session.commit()

    result = simulate_foncier_year(session, p, 2026, tmi=0.30)
    # Aucune charge saisie : seul le forfait de 20 euros/lot s'applique.
    assert result.reel.charges_deductibles_hors_interets == 20.0
    assert result.reel.resultat_imposable == pytest.approx(4_980.0)


def test_reel_deficit_separe_part_interets_sous_plafond(session):
    # loyers=5000, charges hors interets (dont forfait 20) = 8000, interets=3000.
    # resultat_hors_interets = -3000 -> deficit hors interets = 3000, sous le
    # plafond de 10700 -> entierement impute sur le revenu global.
    # resultat_total = -6000 -> reste 3000 (la part liee aux interets) reportable
    # uniquement sur les revenus fonciers.
    p = _make_property(session)
    session.add(_loyer(p.id, 5_000, 2026))
    session.add(
        Expense(
            property_id=p.id, date_paiement=date(2026, 3, 1), montant_ttc=7_980,
            categorie="taxe_fonciere",
        )
    )
    session.add(
        Expense(
            property_id=p.id, date_paiement=date(2026, 4, 1), montant_ttc=3_000,
            categorie="interets_emprunt",
        )
    )
    session.commit()

    result = simulate_foncier_year(session, p, 2026, tmi=0.30)
    reel = result.reel

    assert reel.charges_deductibles_hors_interets == 8_000.0  # 7980 + 20 forfait
    assert reel.interets_emprunt == 3_000.0
    assert reel.resultat_total == -6_000.0
    assert reel.deficit_imputable_revenu_global == 3_000.0
    assert reel.deficit_restant_report_fonciers == 3_000.0
    assert reel.resultat_imposable == 0.0


def test_reel_deficit_hors_interets_plafonne_a_10700(session):
    # resultat_hors_interets tres negatif (-15000), interets=2000.
    # deficit_imputable_global = min(10700, 15000) = 10700.
    # reste reportable sur fonciers = 17000 - 10700 = 6300.
    p = _make_property(session)
    session.add(_loyer(p.id, 1_000, 2026))
    session.add(
        Expense(
            property_id=p.id, date_paiement=date(2026, 3, 1), montant_ttc=15_980,
            categorie="taxe_fonciere",
        )
    )
    session.add(
        Expense(
            property_id=p.id, date_paiement=date(2026, 4, 1), montant_ttc=2_000,
            categorie="interets_emprunt",
        )
    )
    session.commit()

    result = simulate_foncier_year(session, p, 2026, tmi=0.30)
    reel = result.reel

    assert reel.deficit_imputable_revenu_global == 10_700.0
    assert reel.deficit_restant_report_fonciers == pytest.approx(6_300.0)


def test_reel_profit_impute_vieux_deficit_fonciers_annee_suivante(session):
    # Deficit hors interets de 15700 (> plafond 10700) : 10700 impute sur le
    # revenu global, le reste (5000) reporte uniquement sur les fonciers.
    p = _make_property(session)
    session.add(_loyer(p.id, 1_000, 2026))
    session.add(
        Expense(
            property_id=p.id, date_paiement=date(2026, 3, 1), montant_ttc=16_680,
            categorie="taxe_fonciere",
        )
    )
    session.commit()

    r2026 = simulate_foncier_year(session, p, 2026, tmi=0.30).reel
    assert r2026.resultat_imposable == 0.0
    assert r2026.deficit_imputable_revenu_global == 10_700.0
    assert r2026.deficit_restant_report_fonciers == pytest.approx(5_000.0)

    session.add(_loyer(p.id, 20_000, 2027))
    session.commit()

    r2027 = simulate_foncier_year(session, p, 2027, tmi=0.30).reel
    # 20000 - 20 (forfait) - 5000 (vieux deficit impute) = 14980
    assert r2027.deficit_restant_report_fonciers == 0.0
    assert r2027.resultat_imposable == pytest.approx(14_980.0)
