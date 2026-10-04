from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from ..db import get_session
from ..deps import get_the_property, templates
from ..services.simulator import simulate_year

router = APIRouter(prefix="/appartement/simulateur")


@router.get("")
def simulateur(
    request: Request,
    annee: int | None = None,
    tmi_pct: float = 30.0,
    session: Session = Depends(get_session),
):
    property_ = get_the_property(session)
    annee = annee or date.today().year

    result = None
    if property_ is not None and property_.id is not None:
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
