"""Simulateur micro-BIC / réel pour le meublé de tourisme (SPEC §4.4).

Le résultat du réel est recalculé par rejeu de tout l'historique depuis le début
de l'activité (date de première mise en location, ou acquisition) jusqu'à
l'année demandée : pas d'état mis en cache à invalider, correct même si des
données passées sont modifiées après coup. Le jeu de données d'un particulier
reste petit, donc ce rejeu est bon marché.

Bandeau à afficher systématiquement côté UI : « Estimation indicative — à
valider avec un professionnel. »
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from sqlmodel import Session, select

from ..fiscal.loader import FiscalParams, MicroBicBareme, load_fiscal_params
from ..models.booking import Booking
from ..models.enums import NatureWorks, StatutBooking
from ..models.expense import Expense
from ..models.furniture import Furniture
from ..models.property import BuildingComponent, Property
from ..models.works import Works
from .amortization import (
    dotation_building_component,
    dotation_furniture,
    dotation_works,
    extra_base_travaux_avant_activite,
    is_furniture_charge_directe,
)

DUREE_REPORT_DEFICIT_ANS = 10


@dataclass
class MicroBicResult:
    applicable: bool
    recettes: float
    abattement_pct: float
    plafond_recettes: float
    revenu_imposable: float
    impot_estime: float
    prelevements_sociaux_estimes: float
    total_estime: float


@dataclass
class ReelYearData:
    annee: int
    resultat_brut: float
    amortissements_theoriques: float
    amortissements_deduits: float
    amortissements_non_deduits_annee: float
    deficit_annee: float
    resultat_imposable: float


@dataclass
class ReelResult:
    annee: int
    recettes: float
    charges_deductibles: float
    amortissements_theoriques: float
    amortissements_deduits_annee: float
    amortissements_non_deduits_annee: float
    resultat_imposable: float
    impot_estime: float
    prelevements_sociaux_estimes: float
    total_estime: float
    cumul_amortissements_pratiques: float
    deficit_restant_report: float
    amortissements_non_deduits_report: float


@dataclass
class SimulationResult:
    annee: int
    recettes: float
    micro_non_classe: MicroBicResult
    micro_classe: MicroBicResult
    reel: ReelResult
    avertissements: List[str] = field(default_factory=list)


def _recettes_annee(session: Session, property_id: int, annee: int) -> float:
    bookings = session.exec(select(Booking).where(Booking.property_id == property_id)).all()
    return sum(
        b.montant_brut
        for b in bookings
        if b.statut == StatutBooking.confirmee and b.date_arrivee.year == annee
    )


def _charges_deductibles_annee(session: Session, property_id: int, annee: int) -> float:
    expenses = session.exec(select(Expense).where(Expense.property_id == property_id)).all()
    total = sum(e.montant_ttc for e in expenses if e.date.year == annee)

    bookings = session.exec(select(Booking).where(Booking.property_id == property_id)).all()
    total += sum(
        b.commission_plateforme
        for b in bookings
        if b.statut == StatutBooking.confirmee and b.date_arrivee.year == annee
    )

    works = session.exec(select(Works).where(Works.property_id == property_id)).all()
    total += sum(
        w.montant_ttc
        for w in works
        if w.nature == NatureWorks.entretien_reparation
        and not w.avant_premiere_mise_en_location
        and w.date.year == annee
    )

    furniture = session.exec(select(Furniture).where(Furniture.property_id == property_id)).all()
    for f in furniture:
        if f.date_achat.year == annee:
            params_achat = load_fiscal_params(f.date_achat.year)
            if is_furniture_charge_directe(f, params_achat):
                total += f.montant_ttc

    return total


def _amortissements_theoriques_annee(session: Session, property_: Property, annee: int) -> float:
    works = session.exec(select(Works).where(Works.property_id == property_.id)).all()
    extra_base = extra_base_travaux_avant_activite(works)

    components = session.exec(
        select(BuildingComponent).where(BuildingComponent.property_id == property_.id)
    ).all()
    total = sum(dotation_building_component(c, property_, extra_base, annee) for c in components)
    total += sum(dotation_works(w, annee) for w in works)

    furniture = session.exec(select(Furniture).where(Furniture.property_id == property_.id)).all()
    for f in furniture:
        params_achat = load_fiscal_params(f.date_achat.year)
        total += dotation_furniture(f, annee, params_achat)

    return total


def _resoudre_annee(
    resultat_brut: float,
    amortissements_theoriques: float,
    stock_amort_non_deduit_entrant: float,
    stock_deficits_entrants: List[Tuple[int, float]],
    annee: int,
) -> Tuple[ReelYearData, float, List[Tuple[int, float]]]:
    """Applique la règle « l'amortissement ne peut pas créer ou augmenter un déficit »
    puis impute les reports des années antérieures (amortissements non déduits :
    illimité ; déficits : 10 ans). Retourne les nouveaux stocks à reporter."""
    if resultat_brut <= 0:
        amortissements_deduits = 0.0
        amortissements_non_deduits_annee = amortissements_theoriques
        resultat_imposable = resultat_brut
        deficit_annee = -resultat_brut
        stock_amort_sortant = stock_amort_non_deduit_entrant + amortissements_non_deduits_annee
        stock_deficits_sortants = list(stock_deficits_entrants)
    else:
        amortissements_deduits = min(amortissements_theoriques, resultat_brut)
        amortissements_non_deduits_annee = amortissements_theoriques - amortissements_deduits
        resultat_apres_amort = resultat_brut - amortissements_deduits

        imputation_vieux_amort = min(stock_amort_non_deduit_entrant, resultat_apres_amort)
        resultat_apres_vieux_amort = resultat_apres_amort - imputation_vieux_amort
        stock_amort_sortant = (
            stock_amort_non_deduit_entrant - imputation_vieux_amort + amortissements_non_deduits_annee
        )

        reste_a_imputer = resultat_apres_vieux_amort
        stock_deficits_sortants = []
        for annee_origine, montant in stock_deficits_entrants:
            if annee_origine <= annee - DUREE_REPORT_DEFICIT_ANS:
                continue  # expiré (déficit imputable 10 ans)
            if reste_a_imputer > 0 and montant > 0:
                imputation = min(montant, reste_a_imputer)
                montant -= imputation
                reste_a_imputer -= imputation
            if montant > 0:
                stock_deficits_sortants.append((annee_origine, montant))

        resultat_imposable = reste_a_imputer
        deficit_annee = 0.0

    if deficit_annee > 0:
        stock_deficits_sortants.append((annee, deficit_annee))

    data = ReelYearData(
        annee=annee,
        resultat_brut=resultat_brut,
        amortissements_theoriques=amortissements_theoriques,
        amortissements_deduits=amortissements_deduits,
        amortissements_non_deduits_annee=amortissements_non_deduits_annee,
        deficit_annee=deficit_annee,
        resultat_imposable=resultat_imposable,
    )
    return data, stock_amort_sortant, stock_deficits_sortants


def _simulate_reel(
    session: Session, property_: Property, annee: int, tmi: float, taux_prelevements_sociaux: float
) -> ReelResult:
    annee_debut = property_.date_debut_amortissement_bati.year
    if annee < annee_debut:
        annee_debut = annee  # bien pas encore en activité : résultat nul

    stock_amort_non_deduit = 0.0
    stock_deficits: List[Tuple[int, float]] = []
    cumul_amortissements_deduits = 0.0
    data_annee_courante: ReelYearData | None = None

    for y in range(annee_debut, annee + 1):
        resultat_brut = _recettes_annee(session, property_.id, y) - _charges_deductibles_annee(
            session, property_.id, y
        )
        amortissements_theoriques = _amortissements_theoriques_annee(session, property_, y)
        data, stock_amort_non_deduit, stock_deficits = _resoudre_annee(
            resultat_brut, amortissements_theoriques, stock_amort_non_deduit, stock_deficits, y
        )
        cumul_amortissements_deduits += data.amortissements_deduits
        data_annee_courante = data

    assert data_annee_courante is not None
    resultat_imposable = max(data_annee_courante.resultat_imposable, 0.0)
    impot_estime = resultat_imposable * tmi
    prelevements = resultat_imposable * taux_prelevements_sociaux

    return ReelResult(
        annee=annee,
        recettes=_recettes_annee(session, property_.id, annee),
        charges_deductibles=_charges_deductibles_annee(session, property_.id, annee),
        amortissements_theoriques=data_annee_courante.amortissements_theoriques,
        amortissements_deduits_annee=data_annee_courante.amortissements_deduits,
        amortissements_non_deduits_annee=data_annee_courante.amortissements_non_deduits_annee,
        resultat_imposable=resultat_imposable,
        impot_estime=impot_estime,
        prelevements_sociaux_estimes=prelevements,
        total_estime=impot_estime + prelevements,
        cumul_amortissements_pratiques=cumul_amortissements_deduits,
        deficit_restant_report=sum(m for _, m in stock_deficits),
        amortissements_non_deduits_report=stock_amort_non_deduit,
    )


def _simulate_micro(
    recettes: float, bareme: MicroBicBareme, tmi: float, taux_prelevements_sociaux: float
) -> MicroBicResult:
    applicable = recettes <= bareme.plafond_recettes
    revenu_imposable = recettes * (1 - bareme.abattement) if applicable else 0.0
    impot_estime = revenu_imposable * tmi if applicable else 0.0
    prelevements = revenu_imposable * taux_prelevements_sociaux if applicable else 0.0
    return MicroBicResult(
        applicable=applicable,
        recettes=recettes,
        abattement_pct=bareme.abattement,
        plafond_recettes=bareme.plafond_recettes,
        revenu_imposable=revenu_imposable,
        impot_estime=impot_estime,
        prelevements_sociaux_estimes=prelevements,
        total_estime=impot_estime + prelevements,
    )


def simulate_year(session: Session, property_: Property, annee: int, tmi: float) -> SimulationResult:
    fiscal_params: FiscalParams = load_fiscal_params(annee)
    recettes = _recettes_annee(session, property_.id, annee)
    taux_ps = fiscal_params.prelevements_sociaux.revenus_bic_lmnp

    micro_non_classe = _simulate_micro(recettes, fiscal_params.meuble_tourisme.micro_bic.non_classe, tmi, taux_ps)
    micro_classe = _simulate_micro(recettes, fiscal_params.meuble_tourisme.micro_bic.classe, tmi, taux_ps)
    reel = _simulate_reel(session, property_, annee, tmi, taux_ps)

    avertissements = list(fiscal_params.unverified_warnings())
    if not micro_non_classe.applicable:
        avertissements.append(
            f"Micro-BIC non classé non applicable : recettes {recettes:.0f} € > "
            f"plafond {micro_non_classe.plafond_recettes:.0f} €"
        )
    if not micro_classe.applicable:
        avertissements.append(
            f"Micro-BIC classé non applicable : recettes {recettes:.0f} € > "
            f"plafond {micro_classe.plafond_recettes:.0f} €"
        )

    return SimulationResult(
        annee=annee,
        recettes=recettes,
        micro_non_classe=micro_non_classe,
        micro_classe=micro_classe,
        reel=reel,
        avertissements=avertissements,
    )
