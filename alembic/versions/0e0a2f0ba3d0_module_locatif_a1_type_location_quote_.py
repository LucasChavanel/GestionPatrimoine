"""module locatif A1: type_location, quote_part, categories charges

Revision ID: 0e0a2f0ba3d0
Revises: 857f79d3487d
Create Date: 2026-10-04 17:27:06.189323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0e0a2f0ba3d0'
down_revision: Union[str, None] = '857f79d3487d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIE_ENUM = sa.Enum(
    'copro_courantes', 'copro_regularisation', 'fonds_travaux', 'taxe_fonciere',
    'assurance_pno', 'frais_gestion', 'menage_linge', 'energie_internet', 'eau',
    'entretien_reparation', 'travaux_amelioration', 'mobilier', 'interets_emprunt',
    'assurance_emprunteur', 'frais_comptable', 'cfe', 'autre', name='categoriecharge',
)

TYPE_LOCATION_ENUM = sa.Enum(
    'meuble_classique', 'meuble_tourisme_classe', 'meuble_tourisme_non_classe', 'nu',
    name='typelocation',
)

# Ancien code -> nouveau code. Les codes absents (taxe_fonciere, eau,
# interets_emprunt, autre) sont identiques dans les deux nomenclatures.
CATEGORIE_MAPPING = {
    'copropriete': 'copro_courantes',
    'assurance': 'assurance_pno',
    'energie': 'energie_internet',
    'internet': 'energie_internet',
    'menage': 'menage_linge',
    'linge': 'menage_linge',
    'entretien': 'entretien_reparation',
    'frais_plateforme_autres': 'frais_gestion',
    'comptabilite': 'frais_comptable',
}


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Remapper les anciennes catégories AVANT de poser la contrainte du nouvel
    #    enum (sinon la contrainte rejetterait les anciennes valeurs).
    for ancien, nouveau in CATEGORIE_MAPPING.items():
        bind.execute(
            sa.text("UPDATE expense SET categorie = :nouveau WHERE categorie = :ancien"),
            {"nouveau": nouveau, "ancien": ancien},
        )

    # 2) Nouvelles colonnes expense (date_paiement nullable pour l'instant, le
    #    temps de la peupler depuis l'ancienne colonne `date`).
    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date_paiement', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('date_echeance', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('periode_debut', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('periode_fin', sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column('montant_recuperable', sa.Float(), nullable=False, server_default=sa.text('0'))
        )

    bind.execute(sa.text("UPDATE expense SET date_paiement = date"))

    # 3) date_paiement devient obligatoire, categorie bascule vers le nouvel enum,
    #    l'ancienne colonne `date` est supprimée.
    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.alter_column('date_paiement', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column(
            'categorie', existing_type=sa.VARCHAR(length=23), type_=CATEGORIE_ENUM, existing_nullable=False
        )
        batch_op.drop_column('date')

    # 4) property : quote_part=1.0 par défaut (constant), type_location dérivé de
    #    statut_classement par ligne (pas un défaut constant, donc nullable puis peuplé).
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type_location', TYPE_LOCATION_ENUM, nullable=True))
        batch_op.add_column(
            sa.Column('quote_part', sa.Float(), nullable=False, server_default=sa.text('1'))
        )

    bind.execute(
        sa.text(
            "UPDATE property SET type_location = CASE WHEN statut_classement = 'classe' "
            "THEN 'meuble_tourisme_classe' ELSE 'meuble_tourisme_non_classe' END"
        )
    )

    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.alter_column('type_location', existing_type=TYPE_LOCATION_ENUM, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.drop_column('quote_part')
        batch_op.drop_column('type_location')

    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.add_column(sa.Column('date', sa.Date(), nullable=True))

    op.get_bind().execute(sa.text("UPDATE expense SET date = date_paiement"))

    with op.batch_alter_table('expense', schema=None) as batch_op:
        batch_op.alter_column('date', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column(
            'categorie', existing_type=CATEGORIE_ENUM, type_=sa.VARCHAR(length=23), existing_nullable=False
        )
        batch_op.drop_column('montant_recuperable')
        batch_op.drop_column('periode_fin')
        batch_op.drop_column('periode_debut')
        batch_op.drop_column('date_echeance')
        batch_op.drop_column('date_paiement')
