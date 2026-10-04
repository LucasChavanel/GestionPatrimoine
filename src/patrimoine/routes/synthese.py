from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..models.booking import Booking
from ..models.expense import Expense
from ..models.property import Property
from ..services.synthese import compute_synthese

router = APIRouter(prefix="/biens/{property_id}/synthese")


@router.get("")
def synthese(
    property_id: int,
    request: Request,
    annee: int | None = None,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    annees_bookings = session.exec(
        select(Booking.date_paiement).where(Booking.property_id == property_id)
    ).all()
    annees_expenses = session.exec(
        select(Expense.date_paiement).where(Expense.property_id == property_id)
    ).all()
    annees_disponibles = sorted(
        {d.year for d in annees_bookings if d is not None} | {d.year for d in annees_expenses}
    ) or [date.today().year]

    annee = annee or date.today().year
    result = compute_synthese(session, property_, annee)

    return templates.TemplateResponse(
        request,
        "property/synthese.html",
        {
            "property_": property_,
            "annee": annee,
            "annees_disponibles": annees_disponibles,
            "result": result,
        },
    )
