"""enable pgvector extension

Revision ID: c7a254413b75
Revises: dd456df26fe7
Create Date: 2026-08-18 00:35:20.481986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a254413b75'
down_revision: Union[str, Sequence[str], None] = 'dd456df26fe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
