from typing import Optional

from sqlmodel import Field, SQLModel


class FiscalYearCarryforward(SQLModel, table=True):
    """Deux reports distincts du régime réel LMNP, par année d'origine :
    - deficit_restant : imputable sur les bénéfices BIC de même nature, plafonné à 10 ans.
    - amortissements_non_deduits : report sans limite de durée (amortissement qui n'a pas
      pu être déduit car il aurait créé/aggravé un déficit).
    Le simulateur consomme le déficit restant le plus ancien d'abord (FIFO)."""

    __tablename__ = "fiscal_year_carryforward"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="property.id")

    annee_origine: int
    deficit_initial: float = 0.0
    deficit_restant: float = 0.0
    amortissements_non_deduits: float = 0.0
