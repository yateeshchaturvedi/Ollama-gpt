"""Create pgcrypto extension if not exists

Revision ID: e15f2dc87e6a
Revises: d06281cb4bdb
Create Date: 2026-06-12 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e15f2dc87e6a'
down_revision: Union[str, Sequence[str], None] = 'd06281cb4bdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')


def downgrade() -> None:
    # We do not drop pgcrypto as other parts of the DB or other applications might depend on it.
    pass
