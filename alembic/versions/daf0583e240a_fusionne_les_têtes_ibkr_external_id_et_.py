"""fusionne les têtes IBKR (external_id) et Phase 5 (cash/snapshot/property)

Revision ID: daf0583e240a
Revises: 09656c8bac99, 8532ccbabf56
Create Date: 2026-10-04 22:51:41.845050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'daf0583e240a'
down_revision: Union[str, None] = ('09656c8bac99', '8532ccbabf56')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
