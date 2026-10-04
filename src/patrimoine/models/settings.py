from datetime import datetime

from sqlmodel import Field, SQLModel


class AppSettings(SQLModel, table=True):
    """Table singleton (une seule ligne, id=1) pour les réglages applicatifs."""

    __tablename__ = "app_settings"

    id: int | None = Field(default=1, primary_key=True)
    last_backup_at: datetime | None = None
