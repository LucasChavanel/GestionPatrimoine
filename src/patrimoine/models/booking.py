from datetime import date

from sqlmodel import Field, Relationship, SQLModel

from .agency import Agency
from .enums import Plateforme, ReversementTaxeSejour, StatutBooking
from .property import Property


class Booking(SQLModel, table=True):
    __tablename__ = "booking"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")
    agency_id: int | None = Field(default=None, foreign_key="agency.id")

    date_arrivee: date
    date_depart: date
    plateforme: Plateforme

    # Tout compris (loyer + ménage), hors taxe de séjour : voir SPEC_patrimoine.md §4.2
    # et la décision prise avec l'utilisateur (agence, commission ~20%, taxe de séjour
    # jamais perçue par l'hôte).
    montant_brut: float
    commission_plateforme: float = 0.0

    # Date d'encaissement effectif (distincte du séjour). Détermine l'année/mois de
    # reconnaissance de la recette en comptabilité de caisse (dashboard, simulateur) :
    # tant qu'elle n'est pas renseignée, la réservation n'est pas encore une recette.
    date_paiement: date | None = None

    # Champs informatifs uniquement — n'entrent dans aucun calcul de net encaissé
    # ni de recette fiscale, pour éviter un double comptage avec montant_brut.
    taxe_sejour_collectee: float = 0.0
    taxe_sejour_reversee_par: ReversementTaxeSejour | None = None
    frais_menage_factures: float = 0.0

    statut: StatutBooking = StatutBooking.confirmee
    notes: str | None = None

    property_: Property = Relationship(back_populates="bookings")
    agency: Agency | None = Relationship()

    @property
    def nuits(self) -> int:
        return (self.date_depart - self.date_arrivee).days

    @property
    def net_encaisse(self) -> float:
        return self.montant_brut - self.commission_plateforme

    @property
    def est_encaisse(self) -> bool:
        return self.date_paiement is not None
