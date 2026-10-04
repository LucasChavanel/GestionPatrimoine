"""Simulateur micro-foncier / foncier réel pour la location nue (SPEC §Phase C).

Pas d'amortissement en foncier réel (contrairement au LMNP) : le moteur
dotation_annuelle n'intervient pas ici. La subtilité propre à ce régime est la
séparation de la part du déficit liée aux intérêts d'emprunt, qui n'est jamais
imputable sur le revenu global — seulement reportable sur les revenus fonciers
des 10 années suivantes.

Même principe que services/simulator.py : le résultat est recalculé par rejeu
de tout l'historique depuis le début d'activité, pas d'état mis en cache.

Bandeau à afficher systématiquement côté UI : « Estimation indicative — à
valider avec un professionnel. »
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..fiscal.loader import FiscalParams, load_fiscal_params
from ..models.booking import Booking
from ..models.enums import CategorieCharge, StatutBooking
from ..models.expense import Expense
from ..models.property import Property

DUREE_REPORT_DEFICIT_ANS = 10


@dataclass
class MicroFoncierResult:
    applicable: bool
    recettes: float
    abattement_pct: float
    plafond_recettes: float
    revenu_imposable: float
    impot_estime: float
    prelevements_sociaux_estimes: float
    total_estime: float


@dataclass
class FoncierYearData:
    annee: int
    resultat_hors_interets: float
    interets_emprunt: float
    resultat_total: float
    deficit_imputable_revenu_global: float
    resultat_imposable: float


@dataclass
class FoncierReelResult:
    annee: int
    recettes: float
    charges_deductibles_hors_interets: float
    interets_emprunt: float
    resultat_total: float
    deficit_imputable_revenu_global: float
    resultat_imposable: float
    impot_estime: float
    prelevements_sociaux_estimes: float
    total_estime: float
    deficit_restant_report_fonciers: float


@dataclass
class FoncierSimulationResult:
    annee: int
    recettes: float
    micro_foncier: MicroFoncierResult
    reel: FoncierReelResult
    avertissements: list[str] = field(default_factory=list)


def _loyers_annee(session: Session, property_: Property, annee: int) -> float:
    """Même logique de comptabilité de caisse que le LMNP (services/simulator.py) :
    reconnu à l'encaissement, mis à l'échelle par quote_part."""
    bookings = session.exec(select(Booking).where(Booking.property_id == property_.id)).all()
    brut = sum(
        b.montant_brut
        for b in bookings
        if b.statut == StatutBooking.confirmee
        and b.date_paiement is not None
        and b.date_paiement.year == annee
    )
    return brut * property_.quote_part


def _categorie_deductible_foncier(expense: Expense, fiscal_params: FiscalParams) -> bool:
    traitement = fiscal_params.categories_charges.get(expense.categorie.value)
    if traitement is None:
        return True
    return traitement.foncier_reel in ("deductible", "a_qualifier")


def _charges_annee(
    session: Session, property_: Property, annee: int, fiscal_params_annee: FiscalParams
) -> tuple[float, float]:
    """Retourne (charges déductibles hors intérêts, intérêts d'emprunt) de l'année,
    mis à l'échelle par quote_part. Le forfait de frais de gestion (20 €/lot) est
    toujours ajouté, qu'une charge frais_gestion réelle soit saisie ou non."""
    expenses = session.exec(select(Expense).where(Expense.property_id == property_.id)).all()

    hors_interets = fiscal_params_annee.foncier.reel.frais_gestion_forfaitaire_par_lot
    interets = 0.0
    for e in expenses:
        if e.date_paiement.year != annee:
            continue
        fiscal_params_charge = load_fiscal_params(e.date_paiement.year)
        if not _categorie_deductible_foncier(e, fiscal_params_charge):
            continue
        if e.categorie == CategorieCharge.interets_emprunt:
            interets += e.montant_ttc
        else:
            hors_interets += e.montant_ttc

    return hors_interets * property_.quote_part, interets * property_.quote_part


def _avertissements_charges_a_qualifier(session: Session, property_: Property, annee: int) -> list[str]:
    expenses = session.exec(select(Expense).where(Expense.property_id == property_.id)).all()
    fiscal_params = load_fiscal_params(annee)
    nb_a_qualifier = sum(
        1
        for e in expenses
        if e.date_paiement.year == annee
        and fiscal_params.categories_charges.get(e.categorie.value) is not None
        and fiscal_params.categories_charges[e.categorie.value].foncier_reel == "a_qualifier"
    )
    if nb_a_qualifier == 0:
        return []
    return [
        f"{nb_a_qualifier} charge(s) en catégorie 'autre' pour {annee} : à qualifier "
        "manuellement, comptées comme déductibles par défaut en attendant."
    ]


def _resoudre_annee_foncier(
    resultat_hors_interets: float,
    interets_emprunt: float,
    stock_deficits_entrants: list[tuple[int, float]],
    plafond_deficit_global: float,
    annee: int,
) -> tuple[FoncierYearData, list[tuple[int, float]]]:
    """Sépare la part du déficit imputable sur le revenu global (hors intérêts,
    plafonnée) de la part reportable uniquement sur les revenus fonciers futurs
    (le reste, y compris la totalité des intérêts si le résultat hors intérêts
    était positif)."""
    resultat_total = resultat_hors_interets - interets_emprunt

    if resultat_total >= 0:
        reste_a_imputer = resultat_total
        stock_sortant: list[tuple[int, float]] = []
        for annee_origine, montant in stock_deficits_entrants:
            if annee_origine <= annee - DUREE_REPORT_DEFICIT_ANS:
                continue  # expiré (report foncier limité à 10 ans)
            if reste_a_imputer > 0 and montant > 0:
                imputation = min(montant, reste_a_imputer)
                montant -= imputation
                reste_a_imputer -= imputation
            if montant > 0:
                stock_sortant.append((annee_origine, montant))
        resultat_imposable = reste_a_imputer
        deficit_imputable_global = 0.0
    else:
        deficit_imputable_global = min(plafond_deficit_global, max(0.0, -resultat_hors_interets))
        deficit_restant_fonciers = -resultat_total - deficit_imputable_global
        resultat_imposable = 0.0
        stock_sortant = list(stock_deficits_entrants)
        if deficit_restant_fonciers > 0:
            stock_sortant.append((annee, deficit_restant_fonciers))

    data = FoncierYearData(
        annee=annee,
        resultat_hors_interets=resultat_hors_interets,
        interets_emprunt=interets_emprunt,
        resultat_total=resultat_total,
        deficit_imputable_revenu_global=deficit_imputable_global,
        resultat_imposable=resultat_imposable,
    )
    return data, stock_sortant


def _simulate_reel_foncier(
    session: Session, property_: Property, annee: int, tmi: float, taux_prelevements_sociaux: float
) -> FoncierReelResult:
    annee_debut = property_.date_debut_amortissement_bati.year
    if annee < annee_debut:
        annee_debut = annee

    stock_deficits: list[tuple[int, float]] = []
    data_annee_courante: FoncierYearData | None = None

    for y in range(annee_debut, annee + 1):
        fiscal_params_y = load_fiscal_params(y)
        loyers = _loyers_annee(session, property_, y)
        hors_interets, interets = _charges_annee(session, property_, y, fiscal_params_y)
        resultat_hors_interets = loyers - hors_interets
        data, stock_deficits = _resoudre_annee_foncier(
            resultat_hors_interets,
            interets,
            stock_deficits,
            fiscal_params_y.foncier.reel.plafond_deficit_imputable_revenu_global,
            y,
        )
        data_annee_courante = data

    assert data_annee_courante is not None
    resultat_imposable = max(data_annee_courante.resultat_imposable, 0.0)
    impot_estime = resultat_imposable * tmi
    prelevements = resultat_imposable * taux_prelevements_sociaux

    hors_interets_annee, interets_annee = _charges_annee(
        session, property_, annee, load_fiscal_params(annee)
    )

    return FoncierReelResult(
        annee=annee,
        recettes=_loyers_annee(session, property_, annee),
        charges_deductibles_hors_interets=hors_interets_annee,
        interets_emprunt=interets_annee,
        resultat_total=data_annee_courante.resultat_total,
        deficit_imputable_revenu_global=data_annee_courante.deficit_imputable_revenu_global,
        resultat_imposable=resultat_imposable,
        impot_estime=impot_estime,
        prelevements_sociaux_estimes=prelevements,
        total_estime=impot_estime + prelevements,
        deficit_restant_report_fonciers=sum(m for _, m in stock_deficits),
    )


def _simulate_micro_foncier(
    recettes: float, bareme, tmi: float, taux_prelevements_sociaux: float
) -> MicroFoncierResult:
    applicable = recettes <= bareme.plafond_recettes
    revenu_imposable = recettes * (1 - bareme.abattement) if applicable else 0.0
    impot_estime = revenu_imposable * tmi if applicable else 0.0
    prelevements = revenu_imposable * taux_prelevements_sociaux if applicable else 0.0
    return MicroFoncierResult(
        applicable=applicable,
        recettes=recettes,
        abattement_pct=bareme.abattement,
        plafond_recettes=bareme.plafond_recettes,
        revenu_imposable=revenu_imposable,
        impot_estime=impot_estime,
        prelevements_sociaux_estimes=prelevements,
        total_estime=impot_estime + prelevements,
    )


def simulate_foncier_year(
    session: Session, property_: Property, annee: int, tmi: float
) -> FoncierSimulationResult:
    fiscal_params = load_fiscal_params(annee)
    recettes = _loyers_annee(session, property_, annee)
    taux_ps = fiscal_params.prelevements_sociaux.revenus_fonciers

    micro_foncier = _simulate_micro_foncier(recettes, fiscal_params.foncier.micro_foncier, tmi, taux_ps)
    reel = _simulate_reel_foncier(session, property_, annee, tmi, taux_ps)

    avertissements = list(fiscal_params.unverified_warnings_foncier())
    avertissements.extend(_avertissements_charges_a_qualifier(session, property_, annee))
    if not micro_foncier.applicable:
        avertissements.append(
            f"Micro-foncier non applicable : recettes {recettes:.0f} € > "
            f"plafond {micro_foncier.plafond_recettes:.0f} €"
        )
    if reel.deficit_imputable_revenu_global > 0:
        avertissements.append(
            f"{reel.deficit_imputable_revenu_global:.0f} € de déficit imputables sur le revenu "
            "global (hors de ce calcul foncier, qui ne porte que sur l'impôt foncier lui-même)."
        )

    return FoncierSimulationResult(
        annee=annee,
        recettes=recettes,
        micro_foncier=micro_foncier,
        reel=reel,
        avertissements=avertissements,
    )
