from datetime import date

from sqlmodel import Field, SQLModel

from .enums import AllocationCategorie


class Security(SQLModel, table=True):
    """Référence d'un titre (une ligne par ISIN), réutilisée par toutes les
    InvestmentTransaction dessus — évite de dupliquer ticker/classification/cours
    sur chaque opération."""

    __tablename__ = "security"

    id: int | None = Field(default=None, primary_key=True)
    isin: str = Field(index=True, unique=True)
    nom: str
    ticker_yahoo: str | None = None

    # Saisie manuelle — sert à l'allocation cible 80/20 World/Europe (PEA).
    categorie_allocation: AllocationCategorie | None = None

    # Filet de sécurité : rempli à la main en attendant la récupération
    # automatique (Yahoo Finance), puis mis à jour automatiquement ensuite.
    # L'app reste utilisable si la source externe est injoignable.
    dernier_cours: float | None = None
    dernier_cours_devise: str | None = None
    dernier_cours_date: date | None = None
