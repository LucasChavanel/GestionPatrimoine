from datetime import date

from sqlmodel import Field, Relationship, SQLModel

from .enums import CategorieCharge, Recurrence
from .property import Property


class Expense(SQLModel, table=True):
    __tablename__ = "expense"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    # Détermine l'année fiscale de rattachement (comptabilité de caisse, comme
    # Booking.date_paiement). date_echeance est purement informatif (exigibilité
    # de l'appel), n'entre dans aucun calcul.
    date_paiement: date
    date_echeance: date | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None

    montant_ttc: float
    # Part de montant_ttc refacturable au locataire (ex. charges récupérables
    # d'un appel de copropriété). Purement informatif pour l'instant — n'affecte
    # pas la déductibilité, qui porte sur montant_ttc dans sa totalité.
    montant_recuperable: float = 0.0

    fournisseur: str | None = None
    description: str | None = None
    categorie: CategorieCharge

    recurrence: Recurrence = Recurrence.aucune
    recurrence_fin: date | None = None
    # Si cette charge a été générée automatiquement à partir d'une charge récurrente.
    parent_expense_id: int | None = Field(default=None, foreign_key="expense.id")

    property_: Property = Relationship(back_populates="expenses")
