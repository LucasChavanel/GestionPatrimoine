import csv
import io
from datetime import date

from patrimoine.models.booking import Booking
from patrimoine.models.coownership import CoOwnershipYear
from patrimoine.models.enums import (
    Courtier,
    EnvelopeType,
    Plateforme,
    StatutBooking,
    TypeLocation,
    TypeTransaction,
)
from patrimoine.models.expense import Expense
from patrimoine.models.investment_account import InvestmentAccount
from patrimoine.models.investment_transaction import InvestmentTransaction
from patrimoine.models.property import Property
from patrimoine.services.declaration import (
    compute_recap_annee,
    compute_recap_global,
    export_csv_charges_recettes,
    export_recap_csv,
    export_recap_markdown,
)


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


def _booking(property_id, montant_brut, annee, mois=6, date_paiement=None):
    date_paiement = date_paiement or date(annee, mois, 1)
    return Booking(
        property_id=property_id,
        date_arrivee=date(annee, mois, 1),
        date_depart=date(annee, mois, 8),
        plateforme=Plateforme.airbnb,
        montant_brut=montant_brut,
        statut=StatutBooking.confirmee,
        date_paiement=date_paiement,
    )


def test_case_meuble_tourisme_non_classe(session):
    p = _make_property(session, nom="Non classé", type_location=TypeLocation.meuble_tourisme_non_classe)
    session.add(_booking(p.id, 5000, 2026))
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    micro = [ligne for ligne in lignes if ligne.regime == "micro-BIC" and ligne.property_nom == "Non classé"]
    assert len(micro) == 1
    assert micro[0].case == "5NH"
    assert micro[0].montant == 5000


def test_case_meuble_tourisme_classe(session):
    p = _make_property(session, nom="Classé", type_location=TypeLocation.meuble_tourisme_classe)
    session.add(_booking(p.id, 5000, 2026))
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    micro = [ligne for ligne in lignes if ligne.regime == "micro-BIC" and ligne.property_nom == "Classé"]
    assert len(micro) == 1
    assert micro[0].case == "5NG"


def test_case_meuble_classique(session):
    p = _make_property(session, nom="Classique", type_location=TypeLocation.meuble_classique)
    session.add(_booking(p.id, 5000, 2026))
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    micro = [ligne for ligne in lignes if ligne.regime == "micro-BIC" and ligne.property_nom == "Classique"]
    assert len(micro) == 1
    assert micro[0].case == "5NI"


def test_case_nu_micro_foncier(session):
    p = _make_property(session, nom="Nu", type_location=TypeLocation.nu)
    session.add(_booking(p.id, 5000, 2026))
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    micro = [ligne for ligne in lignes if ligne.regime == "micro-foncier"]
    assert len(micro) == 1
    assert micro[0].case == "4BE"


def test_micro_non_applicable_ligne_absente(session):
    # Non classé, plafond 15000 depasse -> pas de ligne micro-BIC pour ce bien.
    p = _make_property(session, nom="Trop gros", type_location=TypeLocation.meuble_tourisme_non_classe)
    session.add(_booking(p.id, 20000, 2026))
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    micro = [ligne for ligne in lignes if ligne.regime == "micro-BIC" and ligne.property_nom == "Trop gros"]
    assert micro == []
    # La ligne "reel" (liasse 2031) reste toujours presente.
    reel = [ligne for ligne in lignes if ligne.regime == "réel" and ligne.property_nom == "Trop gros"]
    assert len(reel) == 1


def test_deficit_foncier_reparti_4bb_4bc(session):
    # Reprend le scenario de test_foncier.py::test_reel_deficit_separe_part_interets_sous_plafond :
    # deficit hors interets 3000 (sous le plafond 10700) -> entierement 4BC,
    # part liee aux interets 3000 -> reportable uniquement sur les fonciers (4BB).
    p = _make_property(session, nom="Deficit", type_location=TypeLocation.nu)
    session.add(_booking(p.id, 5_000, 2026))
    session.add(
        Expense(property_id=p.id, date_paiement=date(2026, 3, 1), montant_ttc=7_980, categorie="taxe_fonciere")
    )
    session.add(
        Expense(property_id=p.id, date_paiement=date(2026, 4, 1), montant_ttc=3_000, categorie="interets_emprunt")
    )
    session.commit()

    lignes = compute_recap_annee(session, 2026)
    lignes_bien = [ligne for ligne in lignes if ligne.property_nom == "Deficit"]

    imputable = [ligne for ligne in lignes_bien if ligne.case == "4BC"]
    report = [ligne for ligne in lignes_bien if ligne.case == "4BB"]
    positif = [ligne for ligne in lignes_bien if ligne.case == "4BA"]

    assert len(imputable) == 1
    assert imputable[0].montant == 3000.0
    assert len(report) == 1
    assert report[0].montant == 3000.0
    assert positif == []


def test_export_csv_charges_recettes_bien_forme(session):
    p = _make_property(session, nom="CSV Test", type_location=TypeLocation.meuble_tourisme_non_classe)
    session.add(_booking(p.id, 1000, 2026))
    session.add(
        Expense(property_id=p.id, date_paiement=date(2026, 2, 1), montant_ttc=200, categorie="taxe_fonciere", fournisseur="Impots")
    )
    session.commit()

    contenu = export_csv_charges_recettes(session, 2026)
    rows = list(csv.reader(io.StringIO(contenu), delimiter=";"))

    assert rows[0] == [
        "bien", "type", "date_paiement", "categorie", "montant", "montant_recuperable", "fournisseur", "description",
    ]
    data_rows = rows[1:]
    assert len(data_rows) == 2
    recette = next(r for r in data_rows if r[1] == "recette")
    charge = next(r for r in data_rows if r[1] == "charge")
    assert recette[0] == "CSV Test"
    assert recette[4] == "1000.00"
    assert charge[4] == "200.00"
    assert charge[6] == "Impots"


def test_export_recap_csv_bien_forme(session):
    p = _make_property(session, nom="Recap CSV", type_location=TypeLocation.meuble_tourisme_non_classe)
    session.add(_booking(p.id, 1000, 2026))
    session.commit()

    contenu = export_recap_csv(session, 2026)
    rows = list(csv.reader(io.StringIO(contenu), delimiter=";"))

    assert rows[0] == ["bien", "regime", "case", "libelle", "montant"]
    assert any(r[0] == "Recap CSV" and r[2] == "5NH" for r in rows[1:])


def test_recap_global_inclut_investissements_3916_indivision(session):
    _make_property(session, nom="Bien", type_location=TypeLocation.meuble_tourisme_non_classe)

    compte = InvestmentAccount(nom="CTO IBKR", type=EnvelopeType.cto, courtier=Courtier.ibkr, date_ouverture=date(2024, 1, 1))
    session.add(compte)
    session.commit()
    session.refresh(compte)
    session.add(
        InvestmentTransaction(
            account_id=compte.id, date=date(2026, 3, 1), type=TypeTransaction.dividende,
            montant=100, devise="EUR",
        )
    )

    session.add(
        CoOwnershipYear(
            annee=2026, libelle="Indivision familiale", quote_part_pct=25, revenus_bruts=1000,
            charges=200, montants_proratises=True, montants_a_reporter="case 4BE : 200 €",
        )
    )
    session.commit()

    recap = compute_recap_global(session, 2026)
    assert recap.case_plus_value == "3VG"
    assert recap.case_dividendes == "2DC"
    assert recap.case_credit_impot == "8VL"
    assert recap.dividendes_cto.dividendes_bruts == 100.0
    assert len(recap.comptes_ibkr) == 1
    assert recap.comptes_ibkr[0].nom == "CTO IBKR"
    assert len(recap.indivision) == 1
    assert recap.indivision[0].montants_a_reporter == "case 4BE : 200 €"


def test_export_recap_markdown_bien_forme(session):
    p = _make_property(session, nom="Bien MD", type_location=TypeLocation.meuble_tourisme_non_classe)
    session.add(_booking(p.id, 1000, 2026))
    session.commit()

    contenu = export_recap_markdown(session, 2026)
    assert contenu.startswith("# Récapitulatif déclaration 2026")
    assert "## Biens immobiliers" in contenu
    assert "## Investissements (CTO)" in contenu
    assert "## Comptes à l'étranger (formulaire 3916)" in contenu
    assert "## Indivision" in contenu
    assert "3VG" in contenu
