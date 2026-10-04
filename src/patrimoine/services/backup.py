"""Export / import chiffré (AES-256 via pyzipper) de la base + des documents (SPEC §4.1).

La base SQLite est d'abord sauvegardée via l'API backup de sqlite3 (snapshot
cohérent dans un fichier temporaire), pour ne jamais zipper un fichier WAL en
cours d'écriture.
"""

from __future__ import annotations

import io
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pyzipper
from sqlmodel import Session

from ..config import get_data_dir, get_database_path, get_documents_dir
from ..models.settings import AppSettings


def _snapshot_database(dest_path: Path) -> None:
    source = sqlite3.connect(str(get_database_path()))
    dest = sqlite3.connect(str(dest_path))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()


def build_encrypted_archive(password: str) -> bytes:
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "patrimoine.db"
        _snapshot_database(tmp_db)

        with pyzipper.AESZipFile(
            buffer, "w", compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.write(tmp_db, arcname="patrimoine.db")
            documents_dir = get_documents_dir()
            for file in documents_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, arcname=f"documents/{file.name}")

    buffer.seek(0)
    return buffer.getvalue()


def mark_backup_done(session: Session) -> None:
    settings = session.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
    settings.last_backup_at = datetime.now(UTC)
    session.add(settings)
    session.commit()


class RestoreError(Exception):
    pass


def restore_encrypted_archive(password: str, archive_bytes: bytes) -> None:
    """Remplace la base et les documents actuels par ceux de l'archive.
    Les anciens fichiers sont renommés (jamais supprimés) en cas de besoin de
    récupération manuelle."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            with pyzipper.AESZipFile(io.BytesIO(archive_bytes)) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.extractall(path=tmp_path)
        except RuntimeError as exc:
            raise RestoreError("Mot de passe incorrect ou archive invalide.") from exc

        restored_db = tmp_path / "patrimoine.db"
        if not restored_db.exists():
            raise RestoreError("Archive invalide : patrimoine.db introuvable.")

        data_dir = get_data_dir()
        documents_dir = get_documents_dir()
        suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

        db_path = get_database_path()
        if db_path.exists():
            db_path.rename(data_dir / f"patrimoine.db.avant-restauration-{suffix}")
        if documents_dir.exists() and any(documents_dir.iterdir()):
            documents_dir.rename(data_dir / f"documents.avant-restauration-{suffix}")
            documents_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy(restored_db, db_path)

        restored_documents = tmp_path / "documents"
        if restored_documents.exists():
            for file in restored_documents.iterdir():
                if file.is_file():
                    shutil.copy(file, documents_dir / file.name)
