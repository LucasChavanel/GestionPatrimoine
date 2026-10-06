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

    # Pertinent pour un compte à terme — laissés vides pour un compte
    # courant/livret classique.
    taux_pct: float | None = None
    duree_mois: int | None = None
    date_fin: date | None = None
