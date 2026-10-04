from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session

from .. import db
from ..db import get_session
from ..deps import templates
from ..models.settings import AppSettings
from ..services.backup import (
    RestoreError,
    build_encrypted_archive,
    mark_backup_done,
    restore_encrypted_archive,
)
from ..services.ibkr_credentials import get_credentials, save_credentials

router = APIRouter(prefix="/parametres")


@router.get("")
def parametres(request: Request, session: Session = Depends(get_session)):
    settings = session.get(AppSettings, 1)
    ibkr = get_credentials()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "last_backup_at": settings.last_backup_at if settings else None,
            "erreur_restauration": None,
            "ibkr_token_configure": bool(ibkr.token),
            "ibkr_query_id_configure": bool(ibkr.query_id),
        },
    )


@router.post("/ibkr")
def enregistrer_ibkr(
    token: str | None = Form(None),
    query_id: str | None = Form(None),
):
    save_credentials(token or None, query_id or None)
    return RedirectResponse(url="/parametres", status_code=303)


@router.post("/export")
def exporter(session: Session = Depends(get_session), password: str = Form(...)):
    archive = build_encrypted_archive(password)
    mark_backup_done(session)
    filename = f"patrimoine-sauvegarde-{date.today().isoformat()}.zip"
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def importer(
    request: Request,
    session: Session = Depends(get_session),
    password: str = Form(...),
    archive: UploadFile = Form(...),
):
    content = await archive.read()
    try:
        restore_encrypted_archive(password, content)
    except RestoreError as exc:
        settings = session.get(AppSettings, 1)
        ibkr = get_credentials()
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "last_backup_at": settings.last_backup_at if settings else None,
                "erreur_restauration": str(exc),
                "ibkr_token_configure": bool(ibkr.token),
                "ibkr_query_id_configure": bool(ibkr.query_id),
            },
        )

    db.dispose_engine()
    db.run_migrations()
    return RedirectResponse(url="/parametres", status_code=303)
