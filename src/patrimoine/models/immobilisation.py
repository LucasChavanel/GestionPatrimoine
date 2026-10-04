from datetime import date

from sqlmodel import Field, Relationship, SQLModel

from .enums import NatureImmobilisation
from .property import Property


class Immobilisation(SQLModel, table=True):
    """Travaux amortissables ou mobilier au-dessus du seuil — le bâti reste
    décomposé finement via BuildingComponent, pas ici (voir plan module locatif)."""

    __tablename__ = "immobilisation"

    id: int | None = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    type: NatureImmobilisation
    date_mise_en_service: date
    montant: float
    duree_ans: int

    # Pertinent seulement si type=travaux : intègre le montant à la base
    # amortissable du bâti plutôt que de l'amortir séparément (voir
    # services/amortization.py).
    avant_premiere_mise_en_location: bool = False

    description: str | None = None
    fournisseur: str | None = None
    # Traçabilité vers la charge d'origine, si créée automatiquement depuis une
    # Expense(categorie=travaux_amelioration|mobilier).
    source_expense_id: int | None = Field(default=None, foreign_key="expense.id")

    property_: Property = Relationship(back_populates="immobilisations")
