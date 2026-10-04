
from sqlmodel import Field, SQLModel


class CoOwnershipYear(SQLModel, table=True):
    """Indivision gérée par un tiers qui transmet les chiffres chaque année.
    Pas de gestion détaillée — montants saisis tels que transmis."""

    __tablename__ = "coownership_year"

    id: int | None = Field(default=None, primary_key=True)

    annee: int
    libelle: str  # nom ou libellé du bien / de l'ensemble

    quote_part_pct: float
    revenus_bruts: float
    charges: float
    montants_proratises: bool  # True si revenus_bruts/charges sont déjà à la quote-part

    regime_declare: str | None = None  # texte libre
    montants_a_reporter: str | None = None  # texte libre, saisi tel que transmis
