"""module locatif A2: unifie Immobilisation, retire works et furniture

Revision ID: b62511f31031
Revises: 0e0a2f0ba3d0
Create Date: 2026-10-04 17:39:49.387537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b62511f31031'
down_revision: Union[str, None] = '0e0a2f0ba3d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrer_works(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, property_id, date, montant_ttc, fournisseur, description, nature, "
            "duree_amortissement, avant_premiere_mise_en_location FROM works"
        )
    ).fetchall()

    for (
        works_id, property_id, works_date, montant_ttc, fournisseur, description, nature,
        duree_amortissement, avant_activite,
    ) in rows:
        if nature == "entretien_reparation":
            # Charge directe : devient une Expense(categorie=entretien_reparation).
            # L'ancien flag avant_premiere_mise_en_location n'a plus d'équivalent
            # direct sur Expense, mais le simulateur ne rejoue jamais les années
            # antérieures au début d'activité donc le comportement (non déductible
            # avant activité) reste inchangé.
            result = bind.execute(
                sa.text(
                    "INSERT INTO expense (property_id, date_paiement, montant_ttc, "
                    "montant_recuperable, fournisseur, description, categorie, recurrence) "
                    "VALUES (:pid, :date_paiement, :montant, 0, :fournisseur, :description, "
                    "'entretien_reparation', 'aucune')"
                ),
                {
                    "pid": property_id, "date_paiement": works_date, "montant": montant_ttc,
                    "fournisseur": fournisseur, "description": description,
                },
            )
            nouvel_id = result.lastrowid
            nouveau_type_entite = "expense"
        else:
            # amelioration / construction_agrandissement : devient une Immobilisation.
            duree = duree_amortissement or 15
            result = bind.execute(
                sa.text(
                    "INSERT INTO immobilisation (property_id, type, date_mise_en_service, "
                    "montant, duree_ans, avant_premiere_mise_en_location, description, fournisseur) "
                    "VALUES (:pid, 'travaux', :date_mes, :montant, :duree, :avant, :description, :fournisseur)"
                ),
                {
                    "pid": property_id, "date_mes": works_date, "montant": montant_ttc, "duree": duree,
                    "avant": 1 if avant_activite else 0, "description": description,
                    "fournisseur": fournisseur,
                },
            )
            nouvel_id = result.lastrowid
            nouveau_type_entite = "immobilisation"

        bind.execute(
            sa.text(
                "UPDATE attachment SET entity_type = :nouveau_type, entity_id = :nouvel_id "
                "WHERE entity_type = 'works' AND entity_id = :ancien_id"
            ),
            {"nouveau_type": nouveau_type_entite, "nouvel_id": nouvel_id, "ancien_id": works_id},
        )


def _migrer_furniture(bind) -> None:
    from patrimoine.fiscal.loader import load_fiscal_params

    rows = bind.execute(
        sa.text(
            "SELECT id, property_id, date_achat, montant_ttc, description, duree_amortissement "
            "FROM furniture"
        )
    ).fetchall()

    for furniture_id, property_id, date_achat, montant_ttc, description, duree_amortissement in rows:
        annee_achat = int(str(date_achat)[:4])
        fiscal_params = load_fiscal_params(annee_achat)
        seuil = fiscal_params.meuble_tourisme.amortissement.seuil_charge_directe_mobilier

        if montant_ttc < seuil:
            result = bind.execute(
                sa.text(
                    "INSERT INTO expense (property_id, date_paiement, montant_ttc, "
                    "montant_recuperable, description, categorie, recurrence) "
                    "VALUES (:pid, :date_paiement, :montant, 0, :description, 'mobilier', 'aucune')"
                ),
                {
                    "pid": property_id, "date_paiement": date_achat, "montant": montant_ttc,
                    "description": description,
                },
            )
            nouvel_id = result.lastrowid
            nouveau_type_entite = "expense"
        else:
            result = bind.execute(
                sa.text(
                    "INSERT INTO immobilisation (property_id, type, date_mise_en_service, "
                    "montant, duree_ans, avant_premiere_mise_en_location, description) "
                    "VALUES (:pid, 'mobilier', :date_mes, :montant, :duree, 0, :description)"
                ),
                {
                    "pid": property_id, "date_mes": date_achat, "montant": montant_ttc,
                    "duree": duree_amortissement, "description": description,
                },
            )
            nouvel_id = result.lastrowid
            nouveau_type_entite = "immobilisation"

        bind.execute(
            sa.text(
                "UPDATE attachment SET entity_type = :nouveau_type, entity_id = :nouvel_id "
                "WHERE entity_type = 'furniture' AND entity_id = :ancien_id"
            ),
            {"nouveau_type": nouveau_type_entite, "nouvel_id": nouvel_id, "ancien_id": furniture_id},
        )


def upgrade() -> None:
    op.create_table(
        'immobilisation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('travaux', 'mobilier', name='natureimmobilisation'), nullable=False),
        sa.Column('date_mise_en_service', sa.Date(), nullable=False),
        sa.Column('montant', sa.Float(), nullable=False),
        sa.Column('duree_ans', sa.Integer(), nullable=False),
        sa.Column('avant_premiere_mise_en_location', sa.Boolean(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('fournisseur', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('source_expense_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['property.id'], ),
        sa.ForeignKeyConstraint(['source_expense_id'], ['expense.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    bind = op.get_bind()
    _migrer_works(bind)
    _migrer_furniture(bind)

    op.drop_table('furniture')
    op.drop_table('works')


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('works',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('property_id', sa.INTEGER(), nullable=False),
    sa.Column('date', sa.DATE(), nullable=False),
    sa.Column('montant_ttc', sa.FLOAT(), nullable=False),
    sa.Column('fournisseur', sa.VARCHAR(), nullable=True),
    sa.Column('description', sa.VARCHAR(), nullable=True),
    sa.Column('nature', sa.VARCHAR(length=27), nullable=False),
    sa.Column('duree_amortissement', sa.INTEGER(), nullable=True),
    sa.Column('avant_premiere_mise_en_location', sa.BOOLEAN(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['property.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('furniture',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('property_id', sa.INTEGER(), nullable=False),
    sa.Column('date_achat', sa.DATE(), nullable=False),
    sa.Column('montant_ttc', sa.FLOAT(), nullable=False),
    sa.Column('description', sa.VARCHAR(), nullable=True),
    sa.Column('duree_amortissement', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['property.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.drop_table('immobilisation')
    # ### end Alembic commands ###
