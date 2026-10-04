"""Récapitulatif « lignes à reporter » et export CSV pour un comptable
(Module locatif, Phase D). Aucune nouvelle logique fiscale : on consomme les
résultats déjà calculés par services/simulator.py (LMNP) et services/foncier.py
(foncier), qui restent la seule source de vérité. tmi=0.0 partout : seuls les
montants de base (recettes, résultat imposable) nous intéressent ici, pas
l'impôt estimé — même convention que services/synthese.py."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from sqlmodel import Session, select

from ..fiscal.loader import FiscalParams, load_fiscal_params
from ..models.booking import Booking
from ..models.enums import StatutBooking, TypeLocation
from ..models.expense import Expense
from ..models.property import Property
from .foncier import simulate_foncier_year
from .simulator import simulate_year


@dataclass
class LigneDeclaration:
    property_nom: str
    case: str | None
    libelle: str
    montant: float
    regime: str


def _lignes_meuble(
    session: Session, property_: Property, annee: int, params: FiscalParams
) -> list[LigneDeclaration]:
    result = simulate_year(session, property_, annee, tmi=0.0)
    cases = params.cases_declaration
    lignes: list[LigneDeclaration] = []

    if property_.type_location == TypeLocation.meuble_tourisme_non_classe:
        micro = result.micro_non_classe
        case = cases.meuble_tourisme_non_classe_micro if cases else None
    elif property_.type_location == TypeLocation.meuble_tourisme_classe:
        micro = result.micro_classe
        case = cases.meuble_tourisme_classe_micro if cases else None
    else:  # meuble_classique — même barème que classé (50 %/77 700 €)
        micro = result.micro_classe
        case = cases.meuble_classique_micro if cases else None

    if micro.applicable:
        lignes.append(
            LigneDeclaration(
                property_nom=property_.nom,
                case=case,
                libelle="Recettes brutes (micro-BIC)",
                montant=micro.recettes,
                regime="micro-BIC",
            )
        )

    lignes.append(
        LigneDeclaration(
            property_nom=property_.nom,
            case=None,
            libelle="Résultat imposable (réel — à reporter via la liasse 2031, non générée par cet outil)",
            montant=result.reel.resultat_imposable,
            regime="réel",
        )
    )
    return lignes


def _lignes_foncier(
    session: Session, property_: Property, annee: int, params: FiscalParams
) -> list[LigneDeclaration]:
    result = simulate_foncier_year(session, property_, annee, tmi=0.0)
    cases = params.cases_declaration
    lignes: list[LigneDeclaration] = []

    if result.micro_foncier.applicable:
        lignes.append(
            LigneDeclaration(
                property_nom=property_.nom,
                case=cases.micro_foncier if cases else None,
                libelle="Recettes brutes (micro-foncier)",
                montant=result.micro_foncier.recettes,
                regime="micro-foncier",
            )
        )

    reel = result.reel
    if reel.resultat_imposable > 0:
        lignes.append(
            LigneDeclaration(
                property_nom=property_.nom,
                case=cases.foncier_reel_positif if cases else None,
                libelle="Résultat foncier net imposable (réel)",
                montant=reel.resultat_imposable,
                regime="foncier réel",
            )
        )
    if reel.deficit_imputable_revenu_global > 0:
        lignes.append(
            LigneDeclaration(
                property_nom=property_.nom,
                case=cases.foncier_reel_deficit_imputable_revenu_global if cases else None,
                libelle="Déficit imputable sur le revenu global (≤ 10 700 €/an, hors intérêts)",
                montant=reel.deficit_imputable_revenu_global,
                regime="foncier réel",
            )
        )
    if reel.deficit_restant_report_fonciers > 0:
        lignes.append(
            LigneDeclaration(
                property_nom=property_.nom,
                case=cases.foncier_reel_deficit_report_fonciers if cases else None,
                libelle="Déficit reportable uniquement sur les revenus fonciers (intérêts + surplus)",
                montant=reel.deficit_restant_report_fonciers,
                regime="foncier réel",
            )
        )
    return lignes


def compute_recap_annee(session: Session, annee: int) -> list[LigneDeclaration]:
    params = load_fiscal_params(annee)
    properties = session.exec(select(Property).order_by(Property.nom)).all()
    lignes: list[LigneDeclaration] = []
    for property_ in properties:
        if property_.type_location == TypeLocation.nu:
            lignes.extend(_lignes_foncier(session, property_, annee, params))
        else:
            lignes.extend(_lignes_meuble(session, property_, annee, params))
    return lignes


def export_recap_csv(session: Session, annee: int) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["bien", "regime", "case", "libelle", "montant"])
    for ligne in compute_recap_annee(session, annee):
        writer.writerow(
            [ligne.property_nom, ligne.regime, ligne.case or "", ligne.libelle, f"{ligne.montant:.2f}"]
        )
    return buffer.getvalue()


def export_csv_charges_recettes(session: Session, annee: int) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["bien", "type", "date_paiement", "categorie", "montant", "montant_recuperable", "fournisseur", "description"]
    )

    lignes: list[tuple] = []
    properties = session.exec(select(Property).order_by(Property.nom)).all()
    for property_ in properties:
        bookings = session.exec(select(Booking).where(Booking.property_id == property_.id)).all()
        for b in bookings:
            if (
                b.statut == StatutBooking.confirmee
                and b.date_paiement is not None
                and b.date_paiement.year == annee
            ):
                lignes.append(
                    (property_.nom, "recette", b.date_paiement, "location", b.montant_brut, 0.0, "", "")
                )

        expenses = session.exec(select(Expense).where(Expense.property_id == property_.id)).all()
        for e in expenses:
            if e.date_paiement.year == annee:
                lignes.append(
                    (
                        property_.nom,
                        "charge",
                        e.date_paiement,
                        e.categorie.value,
                        e.montant_ttc,
                        e.montant_recuperable,
                        e.fournisseur or "",
                        e.description or "",
                    )
                )

    lignes.sort(key=lambda t: (t[0], t[2]))
    for nom, type_, date_paiement, categorie, montant, montant_recuperable, fournisseur, description in lignes:
        writer.writerow(
            [nom, type_, date_paiement.isoformat(), categorie, f"{montant:.2f}", f"{montant_recuperable:.2f}", fournisseur, description]
        )
    return buffer.getvalue()
