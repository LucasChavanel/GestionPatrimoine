from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from ..db import get_session
from ..deps import get_property_or_404, templates
from ..models.property import Property
from ..services.simulator import simulate_year

router = APIRouter(prefix="/biens/{property_id}/simulateur")


@router.get("")
def simulateur(
    property_id: int,
    request: Request,
    annee: int | None = None,
    tmi_pct: float = 30.0,
    session: Session = Depends(get_session),
    property_: Property = Depends(get_property_or_404),
):
    annee = annee or date.today().year
    result = simulate_year(session, property_, annee, tmi=tmi_pct / 100)

    return templates.TemplateResponse(
        request,
        "property/simulateur.html",
        {
            "property_": property_,
            "annee": annee,
            "tmi_pct": tmi_pct,
            "result": result,
        },
    )
