from datetime import date

from sqlmodel import Field, SQLModel


class PatrimoineSnapshot(SQLModel, table=True):
    """Historique de valeur du patrimoine consolidé — une ligne par jour (upsert,
    voir services/patrimoine_global.py::enregistrer_snapshot_du_jour)."""

    __tablename__ = "patrimoine_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    date_snapshot: date = Field(index=True, unique=True)
    valeur_actions: float
    valeur_cash: float
    valeur_immobilier: float
    valeur_or: float
    valeur_totale: float
