from datetime import date

from sqlmodel import Field, Relationship, SQLModel

from .enums import Plateforme, ReversementTaxeSejour, StatutBooking
from .property import Property


class Booking(SQLModel, table=True):
    __tablename__ = "booking"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    date_arrivee: date
    date_depart: date
    plateforme: Plateforme

    # Tout compris (loyer + ménage), hors taxe de séjour : voir SPEC_patrimoine.md §4.2
    # et la décision prise avec l'utilisateur (agence, commission ~20%, taxe de séjour
    # jamais perçue par l'hôte).
    montant_brut: float
    commission_plateforme: float = 0.0

    # Champs informatifs uniquement — n'entrent dans aucun calcul de net encaissé
    # ni de recette fiscale, pour éviter un double comptage avec montant_brut.
    taxe_sejour_collectee: float = 0.0
    taxe_sejour_reversee_par: ReversementTaxeSejour | None = None
    frais_menage_factures: float = 0.0

    statut: StatutBooking = StatutBooking.confirmee
    notes: str | None = None

    property_: Property = Relationship(back_populates="bookings")

    @property
    def nuits(self) -> int:
        return (self.date_depart - self.date_arrivee).days

    @property
    def net_encaisse(self) -> float:
        return self.montant_brut - self.commission_plateforme
