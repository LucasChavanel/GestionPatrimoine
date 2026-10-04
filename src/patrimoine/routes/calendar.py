import calendar
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_the_property, templates
from ..models.booking import Booking

router = APIRouter(prefix="/appartement/calendrier")

NOMS_MOIS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


@router.get("")
def calendrier(
    request: Request,
    annee: int | None = None,
    mois: int | None = None,
    session: Session = Depends(get_session),
):
    today = date.today()
    annee = annee or today.year
    mois = mois or today.month

    property_ = get_the_property(session)
    bookings: list[Booking] = []
    if property_ is not None:
        bookings = session.exec(select(Booking).where(Booking.property_id == property_.id)).all()

    semaines = calendar.monthcalendar(annee, mois)
    grille = []
    for semaine in semaines:
        ligne = []
        for jour_num in semaine:
            if jour_num == 0:
                ligne.append(None)
                continue
            jour = date(annee, mois, jour_num)
            reservations_du_jour = [b for b in bookings if b.date_arrivee <= jour < b.date_depart]
            ligne.append({"jour": jour_num, "reservations": reservations_du_jour})
        grille.append(ligne)

    mois_precedent = mois - 1 or 12
    annee_mois_precedent = annee - 1 if mois == 1 else annee
    mois_suivant = mois + 1 if mois < 12 else 1
    annee_mois_suivant = annee + 1 if mois == 12 else annee

    return templates.TemplateResponse(
        request,
        "property/calendrier.html",
        {
            "property_": property_,
            "annee": annee,
            "mois": mois,
            "nom_mois": NOMS_MOIS[mois - 1],
            "grille": grille,
            "mois_precedent": mois_precedent,
            "annee_mois_precedent": annee_mois_precedent,
            "mois_suivant": mois_suivant,
            "annee_mois_suivant": annee_mois_suivant,
        },
    )
