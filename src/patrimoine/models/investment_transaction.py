from datetime import date

from sqlmodel import Field, SQLModel

from .enums import TypeTransaction


class InvestmentTransaction(SQLModel, table=True):
    """Table nommée investment_transaction (pas `transaction`, mot réservé ambigu
    en SQL). Un dépôt/retrait n'a pas de security_id — c'est ce qui permet de
    calculer les versements cumulés PEA sans table séparée (voir services/pea.py)."""

    __tablename__ = "investment_transaction"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="investment_account.id")
    security_id: int | None = Field(default=None, foreign_key="security.id")

    date: date
    type: TypeTransaction

    quantite: float | None = None
    prix_unitaire: float | None = None
    devise: str = "EUR"
    frais: float = 0.0
    montant: float  # montant total de l'opération, hors frais
    description: str | None = None
