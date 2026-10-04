"""Pièces jointes : stockage par hash SHA-256, dédup au niveau fichier (SPEC §4.1)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_documents_dir
from ..models.attachment import Attachment
from ..models.enums import EntityType


def save_attachment(
    session: Session,
    content: bytes,
    original_filename: str,
    content_type: str | None,
    entity_type: EntityType,
    entity_id: int,
) -> Attachment:
    sha256_hash = hashlib.sha256(content).hexdigest()
    ext = Path(original_filename).suffix
    stored_filename = f"{sha256_hash}{ext}"
    dest = get_documents_dir() / stored_filename
    if not dest.exists():
        dest.write_bytes(content)

    attachment = Attachment(
        sha256_hash=sha256_hash,
        stored_filename=stored_filename,
        original_filename=original_filename,
        content_type=content_type,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def list_attachments(session: Session, entity_type: EntityType, entity_id: int) -> list[Attachment]:
    return session.exec(
        select(Attachment).where(
            Attachment.entity_type == entity_type, Attachment.entity_id == entity_id
        )
    ).all()


def delete_attachment(session: Session, attachment_id: int) -> None:
    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        return
    sha256_hash = attachment.sha256_hash
    stored_filename = attachment.stored_filename
    session.delete(attachment)
    session.commit()

    remaining = session.exec(select(Attachment).where(Attachment.sha256_hash == sha256_hash)).all()
    if not remaining:
        path = get_documents_dir() / stored_filename
        if path.exists():
            path.unlink()
