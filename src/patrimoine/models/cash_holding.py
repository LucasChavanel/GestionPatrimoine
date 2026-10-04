from datetime import date

from sqlmodel import Field, SQLModel


class CashHolding(SQLModel, table=True):
    """Cash hors enveloppes d'investissement (compte courant, livret...) — saisie
    manuelle, comme Security.dernier_cours : pas de source automatique."""

    __tablename__ = "cash_holding"

    id: int | None = Field(default=None, primary_key=True)
    nom: str
    solde: float
    devise: str = "EUR"
    date_maj: date
