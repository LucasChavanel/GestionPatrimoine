from datetime import date

import pytest

from patrimoine.models.booking import Booking
from patrimoine.models.enums import NatureComposant, Plateforme, StatutBooking
from patrimoine.models.expense import Expense
from patrimoine.models.property import BuildingComponent, Property
from patrimoine.services.simulator import simulate_year


def _make_property(session, **overrides) -> Property:
    defaults = dict(
        nom="Test",
        adresse="x",
        surface=30,
        date_acquisition=date(2020, 1, 1),
        prix_acquisition=100_000,
        frais_notaire=0,
        part_terrain_pct=0,
        date_premiere_mise_en_location=date(2020, 1, 1),
    )
    defaults.update(overrides)
    p = Property(**defaults)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _booking(property_id, montant_brut, annee, commission=0.0, mois=6, date_paiement=None):
    # Par defaut, payee le jour de l'arrivee : les tests qui ne testent pas
    # specifiquement la logique de date de paiement gardent recette == annee du sejour.
    if date_paiement is None:
        date_paiement = date(annee, mois, 1)
    return Booking(
        property_id=property_id,
        date_arrivee=date(annee, mois, 1),
        date_depart=date(annee, mois, 8),
        plateforme=Plateforme.airbnb,
        montant_brut=montant_brut,
        commission_plateforme=commission,
        statut=StatutBooking.confirmee,
        date_paiement=date_paiement,
    )


def test_micro_bic_applicable_et_abattement(session):
    p = _make_property(session)
    session.add(_booking(p.id, 10_000, 2026))
    session.commit()

    result = simulate_year(session, p, 2026, tmi=0.30)

    assert result.recettes == 10_000
    assert result.micro_non_classe.applicable is True
    assert result.micro_non_classe.revenu_imposable == 7_000  # 10000 * (1 - 0.30)
    assert result.micro_classe.revenu_imposable == 5_000  # 10000 * (1 - 0.50)


def test_micro_bic_non_applicable_si_plafond_depasse(session):
    p = _make_property(session)
    session.add(_booking(p.id, 20_000, 2026))  # > plafond non classe (15000)
    session.commit()

    result = simulate_year(session, p, 2026, tmi=0.30)

    assert result.micro_non_classe.applicable is False
    assert result.micro_non_classe.revenu_imposable == 0.0
    assert any("non applicable" in a for a in result.avertissements)


def test_reel_amortissement_ne_cree_pas_de_deficit(session):
    p = _make_property(session)
    session.add(
        BuildingComponent(
            property_id=p.id, nature=NatureComposant.agencements,
            part_du_prix_pct=100, duree_amortissement=10,
        )
    )
    session.add(_booking(p.id, 5_000, 2020))
    session.commit()

    result = simulate_year(session, p, 2020, tmi=0.30)
    reel = result.reel

    assert reel.recettes == 5_000
    # Amortissement theorique (~10000/an) largement superieur au resultat brut (5000) :
    # il est plafonne pour ne pas creer de deficit.
    assert reel.amortissements_deduits_annee == 5_000
    assert reel.resultat_imposable == 0.0
    assert reel.amortissements_non_deduits_annee > 0
    assert reel.deficit_restant_report == 0.0


def test_reel_deficit_puis_imputation_annee_suivante(session):
    p = _make_property(session)
    session.add(
        BuildingComponent(
            property_id=p.id, nature=NatureComposant.agencements,
            part_du_prix_pct=100, duree_amortissement=10,
        )
    )
    # 2020 : pas de recettes, une charge -> deficit avant amortissement.
    session.add(Expense(property_id=p.id, date=date(2020, 3, 1), montant_ttc=6_000, categorie="autre"))
    session.commit()

    r2020 = simulate_year(session, p, 2020, tmi=0.30).reel
    assert r2020.resultat_imposable == 0.0
    assert r2020.deficit_restant_report == 6_000.0

    # 2022 : recettes largement superieures aux charges + amortissement de l'annee ->
    # le vieux deficit de 2020 doit etre impute sur ce qu'il reste apres amortissement.
    session.add(_booking(p.id, 50_000, 2022))
    session.commit()

    r2022 = simulate_year(session, p, 2022, tmi=0.30).reel
    assert r2022.deficit_restant_report == 0.0
    assert r2022.resultat_imposable > 0


def test_recette_reconnue_a_la_date_de_paiement_pas_au_sejour(session):
    # Sejour du 30 dec 2025 au 3 janv 2026, paye le 1er fevrier 2026 : doit
    # compter comme recette 2026, pas 2025 (comptabilite de caisse du BIC).
    p = _make_property(session, date_premiere_mise_en_location=date(2020, 1, 1))
    session.add(
        Booking(
            property_id=p.id,
            date_arrivee=date(2025, 12, 30),
            date_depart=date(2026, 1, 3),
            plateforme=Plateforme.airbnb,
            montant_brut=1_000.0,
            commission_plateforme=0.0,
            statut=StatutBooking.confirmee,
            date_paiement=date(2026, 2, 1),
        )
    )
    session.commit()

    result_2025 = simulate_year(session, p, 2025, tmi=0.30)
    assert result_2025.recettes == 0.0

    result_2026 = simulate_year(session, p, 2026, tmi=0.30)
    assert result_2026.recettes == 1_000.0


def test_recette_non_encaissee_exclue_des_totaux(session):
    p = _make_property(session)
    session.add(
        Booking(
            property_id=p.id,
            date_arrivee=date(2026, 6, 1),
            date_depart=date(2026, 6, 8),
            plateforme=Plateforme.airbnb,
            montant_brut=1_000.0,
            statut=StatutBooking.confirmee,
            date_paiement=None,  # pas encore paye
        )
    )
    session.commit()

    result = simulate_year(session, p, 2026, tmi=0.30)
    assert result.recettes == 0.0


def test_reel_works_avant_mise_en_location_integre_a_la_base(session):
    from patrimoine.models.enums import NatureWorks
    from patrimoine.models.works import Works

    p = _make_property(session, date_premiere_mise_en_location=date(2020, 9, 1))
    session.add(
        BuildingComponent(
            property_id=p.id, nature=NatureComposant.agencements,
            part_du_prix_pct=100, duree_amortissement=10,
        )
    )
    session.add(
        Works(
            property_id=p.id,
            date=date(2020, 3, 1),
            montant_ttc=50_000,
            nature=NatureWorks.amelioration,
            avant_premiere_mise_en_location=True,
        )
    )
    session.add(_booking(p.id, 100_000, 2021))
    session.commit()

    result = simulate_year(session, p, 2021, tmi=0.30)
    # Base attendue : (100000 batiment + 50000 travaux avant activite) / 10 ans = 15000/an.
    assert result.reel.amortissements_theoriques == pytest.approx(15_000.0, rel=1e-3)
