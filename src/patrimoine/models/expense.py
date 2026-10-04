from datetime import date

from sqlmodel import Field, Relationship, SQLModel

from .enums import CategorieCharge, Recurrence
from .property import Property


class Expense(SQLModel, table=True):
    __tablename__ = "expense"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    date: date
    montant_ttc: float
    fournisseur: str | None = None
    description: str | None = None
    categorie: CategorieCharge

    recurrence: Recurrence = Recurrence.aucune
    recurrence_fin: date | None = None
    # Si cette charge a été générée automatiquement à partir d'une charge récurrente.
    parent_expense_id: int | None = Field(default=None, foreign_key="expense.id")

    property_: Property = Relationship(back_populates="expenses")
