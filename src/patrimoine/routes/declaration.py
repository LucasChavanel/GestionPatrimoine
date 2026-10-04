from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from ..db import get_session
from ..deps import templates
from ..services.declaration import (
    compute_recap_global,
    export_csv_charges_recettes,
    export_recap_csv,
    export_recap_markdown,
)

router = APIRouter(prefix="/declaration")


@router.get("")
def declaration(
    request: Request,
    annee: int | None = None,
    session: Session = Depends(get_session),
):
    annee = annee or date.today().year
    recap = compute_recap_global(session, annee)
    return templates.TemplateResponse(
        request,
        "declaration.html",
        {"annee": annee, "lignes": recap.lignes_biens, "recap": recap, "avertissements": recap.avertissements},
    )


@router.get("/export-charges.csv")
def export_charges(annee: int | None = None, session: Session = Depends(get_session)):
    annee = annee or date.today().year
    contenu = export_csv_charges_recettes(session, annee)
    return Response(
        content=contenu,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="charges-recettes-{annee}.csv"'},
    )


@router.get("/export-recap.csv")
def export_recap(annee: int | None = None, session: Session = Depends(get_session)):
    annee = annee or date.today().year
    contenu = export_recap_csv(session, annee)
    return Response(
        content=contenu,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="recap-declaration-{annee}.csv"'},
    )


@router.get("/export-recap.md")
def export_recap_md(annee: int | None = None, session: Session = Depends(get_session)):
    annee = annee or date.today().year
    contenu = export_recap_markdown(session, annee)
    return Response(
        content=contenu,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="recap-complet-{annee}.md"'},
    )
