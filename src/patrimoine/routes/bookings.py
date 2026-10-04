from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_the_property, templates
from ..models.booking import Booking
from ..models.enums import Plateforme, ReversementTaxeSejour, StatutBooking

router = APIRouter(prefix="/appartement/reservations")


@router.get("")
def liste(request: Request, annee: Optional[int] = None, session: Session = Depends(get_session)):
    property_ = get_the_property(session)
    annee = annee or date.today().year

    bookings: list[Booking] = []
    if property_ is not None:
        bookings = session.exec(
            select(Booking)
            .where(Booking.property_id == property_.id)
            .order_by(Booking.date_arrivee)
        ).all()

    bookings_annee = [b for b in bookings if b.date_arrivee.year == annee]

    recettes_par_mois = [0.0] * 12
    nuits_par_mois = [0] * 12
    for b in bookings_annee:
        if b.statut != StatutBooking.confirmee:
            continue
        recettes_par_mois[b.date_arrivee.month - 1] += b.montant_brut
        nuits_par_mois[b.date_arrivee.month - 1] += b.nuits

    taux_occupation_par_mois = [
        round(100 * nuits_par_mois[m] / calendar.monthrange(annee, m + 1)[1], 1) for m in range(12)
    ]

    annees_disponibles = sorted({b.date_arrivee.year for b in bookings}) or [annee]

    return templates.TemplateResponse(
        request,
        "property/reservations.html",
        {
            "property_": property_,
            "bookings": bookings_annee,
            "annee": annee,
            "annees_disponibles": annees_disponibles,
            "plateformes": list(Plateforme),
            "reversements": list(ReversementTaxeSejour),
            "recettes_par_mois": recettes_par_mois,
            "taux_occupation_par_mois": taux_occupation_par_mois,
            "booking_edit": None,
        },
    )


@router.get("/{booking_id}/modifier")
def modifier_formulaire(booking_id: int, request: Request, session: Session = Depends(get_session)):
    property_ = get_the_property(session)
    booking_edit = session.get(Booking, booking_id)
    annee = booking_edit.date_arrivee.year if booking_edit else date.today().year

    bookings: list[Booking] = []
    if property_ is not None:
        bookings = session.exec(
            select(Booking)
            .where(Booking.property_id == property_.id)
            .order_by(Booking.date_arrivee)
        ).all()
    bookings_annee = [b for b in bookings if b.date_arrivee.year == annee]
    annees_disponibles = sorted({b.date_arrivee.year for b in bookings}) or [annee]

    return templates.TemplateResponse(
        request,
        "property/reservations.html",
        {
            "property_": property_,
            "bookings": bookings_annee,
            "annee": annee,
            "annees_disponibles": annees_disponibles,
            "plateformes": list(Plateforme),
            "reversements": list(ReversementTaxeSejour),
            "recettes_par_mois": [0.0] * 12,
            "taux_occupation_par_mois": [0.0] * 12,
            "booking_edit": booking_edit,
        },
    )


def _form_to_booking(
    booking: Booking,
    date_arrivee: str,
    date_depart: str,
    plateforme: Plateforme,
    montant_brut: float,
    commission_plateforme: float,
    taxe_sejour_collectee: float,
    taxe_sejour_reversee_par: Optional[str],
    frais_menage_factures: float,
    statut: StatutBooking,
    notes: Optional[str],
) -> None:
    booking.date_arrivee = date.fromisoformat(date_arrivee)
    booking.date_depart = date.fromisoformat(date_depart)
    booking.plateforme = plateforme
    booking.montant_brut = montant_brut
    booking.commission_plateforme = commission_plateforme
    booking.taxe_sejour_collectee = taxe_sejour_collectee
    booking.taxe_sejour_reversee_par = (
        ReversementTaxeSejour(taxe_sejour_reversee_par) if taxe_sejour_reversee_par else None
    )
    booking.frais_menage_factures = frais_menage_factures
    booking.statut = statut
    booking.notes = notes or None


@router.post("")
def creer(
    session: Session = Depends(get_session),
    date_arrivee: str = Form(...),
    date_depart: str = Form(...),
    plateforme: Plateforme = Form(...),
    montant_brut: float = Form(...),
    commission_plateforme: float = Form(0.0),
    taxe_sejour_collectee: float = Form(0.0),
    taxe_sejour_reversee_par: Optional[str] = Form(None),
    frais_menage_factures: float = Form(0.0),
    statut: StatutBooking = Form(StatutBooking.confirmee),
    notes: Optional[str] = Form(None),
):
    property_ = get_the_property(session)
    if property_ is None or property_.id is None:
        return RedirectResponse(url="/appartement", status_code=303)

    booking = Booking(property_id=property_.id, date_arrivee=date.today(), date_depart=date.today())
    _form_to_booking(
        booking,
        date_arrivee,
        date_depart,
        plateforme,
        montant_brut,
        commission_plateforme,
        taxe_sejour_collectee,
        taxe_sejour_reversee_par,
        frais_menage_factures,
        statut,
        notes,
    )
    session.add(booking)
    session.commit()
    return RedirectResponse(url=f"/appartement/reservations?annee={booking.date_arrivee.year}", status_code=303)


@router.post("/{booking_id}")
def modifier(
    booking_id: int,
    session: Session = Depends(get_session),
    date_arrivee: str = Form(...),
    date_depart: str = Form(...),
    plateforme: Plateforme = Form(...),
    montant_brut: float = Form(...),
    commission_plateforme: float = Form(0.0),
    taxe_sejour_collectee: float = Form(0.0),
    taxe_sejour_reversee_par: Optional[str] = Form(None),
    frais_menage_factures: float = Form(0.0),
    statut: StatutBooking = Form(StatutBooking.confirmee),
    notes: Optional[str] = Form(None),
):
    booking = session.get(Booking, booking_id)
    if booking is None:
        return RedirectResponse(url="/appartement/reservations", status_code=303)
    _form_to_booking(
        booking,
        date_arrivee,
        date_depart,
        plateforme,
        montant_brut,
        commission_plateforme,
        taxe_sejour_collectee,
        taxe_sejour_reversee_par,
        frais_menage_factures,
        statut,
        notes,
    )
    session.add(booking)
    session.commit()
    return RedirectResponse(url=f"/appartement/reservations?annee={booking.date_arrivee.year}", status_code=303)


@router.post("/{booking_id}/supprimer")
def supprimer(booking_id: int, session: Session = Depends(get_session)):
    booking = session.get(Booking, booking_id)
    annee = booking.date_arrivee.year if booking else date.today().year
    if booking is not None:
        session.delete(booking)
        session.commit()
    return RedirectResponse(url=f"/appartement/reservations?annee={annee}", status_code=303)
