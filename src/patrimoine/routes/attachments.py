from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import Session

from ..config import get_documents_dir
from ..db import get_session
from ..models.enums import EntityType
from ..services.attachments import delete_attachment, save_attachment

router = APIRouter(prefix="/pieces-jointes")


@router.post("/upload")
async def upload(
    session: Session = Depends(get_session),
    entity_type: EntityType = Form(...),
    entity_id: int = Form(...),
    redirect_to: str = Form(...),
    file: UploadFile = Form(...),
):
    content = await file.read()
    if content:
        save_attachment(
            session,
            content=content,
            original_filename=file.filename or "document",
            content_type=file.content_type,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return RedirectResponse(url=redirect_to, status_code=303)


@router.get("/{attachment_id}/telecharger")
def telecharger(attachment_id: int, session: Session = Depends(get_session)):
    from ..models.attachment import Attachment

    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        return RedirectResponse(url="/", status_code=303)
    path = get_documents_dir() / attachment.stored_filename
    return FileResponse(path, filename=attachment.original_filename, media_type=attachment.content_type)


@router.post("/{attachment_id}/supprimer")
def supprimer(attachment_id: int, session: Session = Depends(get_session), redirect_to: str = Form(...)):
    delete_attachment(session, attachment_id)
    return RedirectResponse(url=redirect_to, status_code=303)
