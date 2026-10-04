from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from .enums import NatureWorks
from .property import Property


class Works(SQLModel, table=True):
    __tablename__ = "works"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    date: date
    montant_ttc: float
    fournisseur: Optional[str] = None
    description: Optional[str] = None
    nature: NatureWorks

    # Pertinent seulement si nature amortissable (amelioration / construction_agrandissement)
    # et pas avant_premiere_mise_en_location (sinon intégré à la base du bâti, voir
    # services/amortization.py). Préremplie, modifiable.
    duree_amortissement: Optional[int] = None

    avant_premiere_mise_en_location: bool = False

    property_: Property = Relationship(back_populates="works")

    @property
    def est_amortissable(self) -> bool:
        return self.nature in (NatureWorks.amelioration, NatureWorks.construction_agrandissement)
