from datetime import date

from sqlmodel import Field, SQLModel

from .enums import Courtier, EnvelopeType


class InvestmentAccount(SQLModel, table=True):
    """Une enveloppe d'investissement (PEA, CTO...). Les positions ne sont jamais
    stockées ici — toujours recalculées depuis InvestmentTransaction, voir
    services/positions.py."""

    __tablename__ = "investment_account"

    id: int | None = Field(default=None, primary_key=True)
    nom: str
    type: EnvelopeType
    courtier: Courtier
    devise_base: str = "EUR"
    date_ouverture: date | None = None
