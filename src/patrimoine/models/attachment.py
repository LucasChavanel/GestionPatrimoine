from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from .enums import EntityType


class Attachment(SQLModel, table=True):
    """Pièce jointe polymorphe : rattachée à n'importe quelle entité via
    (entity_type, entity_id). Le fichier physique est stocké une seule fois par hash
    (dédup), sous <data_dir>/documents/<sha256>.<ext> (voir services/attachments.py)."""

    __tablename__ = "attachment"

    id: int | None = Field(default=None, primary_key=True)

    sha256_hash: str = Field(index=True)
    stored_filename: str
    original_filename: str
    content_type: str | None = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    entity_type: EntityType = Field(index=True)
    entity_id: int = Field(index=True)
