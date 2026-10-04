from datetime import date
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from .enums import CategorieCharge, Recurrence
from .property import Property


class Expense(SQLModel, table=True):
    __tablename__ = "expense"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    date: date
    montant_ttc: float
    fournisseur: Optional[str] = None
    description: Optional[str] = None
    categorie: CategorieCharge

    recurrence: Recurrence = Recurrence.aucune
    recurrence_fin: Optional[date] = None
    # Si cette charge a été générée automatiquement à partir d'une charge récurrente.
    parent_expense_id: Optional[int] = Field(default=None, foreign_key="expense.id")

    property_: Property = Relationship(back_populates="expenses")
