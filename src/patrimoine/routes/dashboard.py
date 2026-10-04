from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from ..db import get_session
from ..deps import templates
from ..fiscal.loader import load_fiscal_params
from ..models import AppSettings, Booking, Expense, Property
from ..models.enums import StatutBooking
from ..models.patrimoine_snapshot import PatrimoineSnapshot
from ..services.patrimoine_global import compute_consolide, enregistrer_snapshot_du_jour

router = APIRouter()


@router.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    annee = date.today().year

    properties = session.exec(select(Property).order_by(Property.nom)).all()

    resumes_par_bien = []
    prochaines_reservations: list[Booking] = []
    avertissements = list(load_fiscal_params(annee).unverified_warnings())

    for property_ in properties:
        bookings = session.exec(select(Booking).where(Booking.property_id == property_.id)).all()
        # Comptabilité de caisse : recette reconnue à l'encaissement (date_paiement),
        # pas à la date du séjour. Voir services/simulator.py pour la même logique.
        recettes_annee = (
            sum(
                b.montant_brut
                for b in bookings
                if b.statut == StatutBooking.confirmee
                and b.date_paiement is not None
                and b.date_paiement.year == annee
            )
            * property_.quote_part
        )
        expenses = session.exec(select(Expense).where(Expense.property_id == property_.id)).all()
        charges_annee = (
            sum(e.montant_ttc for e in expenses if e.date_paiement.year == annee) * property_.quote_part
        )

        resumes_par_bien.append(
            {
                "property_": property_,
                "recettes_annee": recettes_annee,
                "charges_annee": charges_annee,
                "resultat_annee": recettes_annee - charges_annee,
            }
        )

        prochaines_reservations.extend(
            b
            for b in bookings
            if b.statut == StatutBooking.confirmee and b.date_depart >= date.today()
        )

        if not property_.numero_declaration_mairie:
            avertissements.append(f"{property_.nom} : numéro de déclaration en mairie non renseigné.")

    prochaines_reservations.sort(key=lambda b: b.date_arrivee)
    prochaines_reservations = prochaines_reservations[:5]

    settings = session.get(AppSettings, 1)

    params = load_fiscal_params(annee)
    consolide = compute_consolide(session, params)
    enregistrer_snapshot_du_jour(session, consolide)
    historique = session.exec(
        select(PatrimoineSnapshot).order_by(PatrimoineSnapshot.date_snapshot)
    ).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "annee": annee,
            "resumes_par_bien": resumes_par_bien,
            "prochaines_reservations": prochaines_reservations,
            "last_backup_at": settings.last_backup_at if settings else None,
            "avertissements": avertissements,
            "consolide": consolide,
            "historique": historique,
        },
    )
