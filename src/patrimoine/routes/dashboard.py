from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_the_property, templates
from ..fiscal.loader import load_fiscal_params
from ..models import AppSettings, Booking, Expense, Property
from ..models.enums import StatutBooking

router = APIRouter()


@router.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    annee = date.today().year

    property_ = get_the_property(session)
    property_ids = session.exec(select(Property.id)).all()

    recettes_annee = 0.0
    charges_annee = 0.0
    prochaines_reservations: list[Booking] = []

    if property_ids:
        bookings = session.exec(select(Booking).where(Booking.property_id.in_(property_ids))).all()
        recettes_annee = sum(
            b.montant_brut
            for b in bookings
            if b.statut == StatutBooking.confirmee and b.date_arrivee.year == annee
        )
        prochaines_reservations = sorted(
            (
                b
                for b in bookings
                if b.statut == StatutBooking.confirmee and b.date_depart >= date.today()
            ),
            key=lambda b: b.date_arrivee,
        )[:5]

        expenses = session.exec(select(Expense).where(Expense.property_id.in_(property_ids))).all()
        charges_annee = sum(e.montant_ttc for e in expenses if e.date.year == annee)

    resultat_annee = recettes_annee - charges_annee

    settings = session.get(AppSettings, 1)

    avertissements = list(load_fiscal_params(annee).unverified_warnings())
    if property_ is not None and not property_.numero_declaration_mairie:
        avertissements.append("Numéro de déclaration en mairie non renseigné.")

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "annee": annee,
            "recettes_annee": recettes_annee,
            "charges_annee": charges_annee,
            "resultat_annee": resultat_annee,
            "prochaines_reservations": prochaines_reservations,
            "last_backup_at": settings.last_backup_at if settings else None,
            "avertissements": avertissements,
        },
    )
