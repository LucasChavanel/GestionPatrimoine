from datetime import date
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from .enums import NatureComposant, StatutClassement, TypeLocation

if TYPE_CHECKING:
    from .booking import Booking
    from .expense import Expense
    from .immobilisation import Immobilisation


class Property(SQLModel, table=True):
    __tablename__ = "property"

    id: int | None = Field(default=None, primary_key=True)
    nom: str
    adresse: str
    surface: float

    date_acquisition: date
    prix_acquisition: float
    frais_notaire: float = 0.0
    part_terrain_pct: float = 0.0  # non amortissable, saisie manuelle

    statut_classement: StatutClassement = StatutClassement.non_classe
    nb_etoiles: int | None = None
    date_classement: date | None = None

    numero_declaration_mairie: str | None = None
    date_premiere_mise_en_location: date | None = None

    # Détermine le régime fiscal applicable (micro-BIC vs foncier) — découplé du
    # statut_classement ci-dessus, qui reste un détail administratif informatif.
    type_location: TypeLocation = TypeLocation.meuble_tourisme_non_classe
    # Quote-part de détention (1.0 = pleine propriété). Appliquée au moment du
    # calcul fiscal (services/simulator.py), pas sur les écrans de saisie bruts.
    quote_part: float = 1.0

    building_components: list["BuildingComponent"] = Relationship(back_populates="property_")
    bookings: list["Booking"] = Relationship(back_populates="property_")
    expenses: list["Expense"] = Relationship(back_populates="property_")
    immobilisations: list["Immobilisation"] = Relationship(back_populates="property_")

    @property
    def base_amortissable(self) -> float:
        """Prix d'acquisition + frais de notaire, hors part du terrain (non amortissable)."""
        return (self.prix_acquisition + self.frais_notaire) * (1 - self.part_terrain_pct / 100)

    @property
    def date_debut_amortissement_bati(self) -> date:
        """L'amortissement du bâti démarre à la mise en service (mise en location),
        pas à l'acquisition si le bien est resté en travaux avant sa première location."""
        return self.date_premiere_mise_en_location or self.date_acquisition


class BuildingComponent(SQLModel, table=True):
    __tablename__ = "building_component"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    nature: NatureComposant
    part_du_prix_pct: float  # saisie manuelle ; somme des composants devrait avoisiner 100%
    duree_amortissement: int  # en années, préremplie depuis le fichier fiscal, modifiable

    property_: Property = Relationship(back_populates="building_components")
