
from sqlmodel import Field, SQLModel


class Agency(SQLModel, table=True):
    """Fiche agence : nom + % de commission par défaut, pour préremplir les
    réservations sans ressaisir le taux à chaque fois (le % reste une
    suggestion, la commission effective est toujours stockée en valeur réelle
    sur la réservation)."""

    __tablename__ = "agency"

    id: int | None = Field(default=None, primary_key=True)
    nom: str
    commission_pct_defaut: float
    notes: str | None = None
