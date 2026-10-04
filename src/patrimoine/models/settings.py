from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AppSettings(SQLModel, table=True):
    """Table singleton (une seule ligne, id=1) pour les réglages applicatifs."""

    __tablename__ = "app_settings"

    id: Optional[int] = Field(default=1, primary_key=True)
    last_backup_at: Optional[datetime] = None
