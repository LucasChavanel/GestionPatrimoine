from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from .property import Property


class Furniture(SQLModel, table=True):
    __tablename__ = "furniture"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    date_achat: date
    montant_ttc: float
    description: Optional[str] = None

    # Préremplie depuis le fichier fiscal (durees_defaut.mobilier), modifiable.
    duree_amortissement: int

    property_: Property = Relationship(back_populates="furniture")
