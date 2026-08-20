"""notes support multiple links

Revision ID: 46d639de5dd0
Revises: 7ac2ee3bc639
Create Date: 2026-08-20 12:00:39.104514

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "46d639de5dd0"
down_revision: str | Sequence[str] | None = "7ac2ee3bc639"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """A note held at most one link (`linked_source`/`linked_url`/
    `linked_title`); it now holds a list (`links` JSONB). Added nullable
    first, backfilled from any existing single link, then locked to
    NOT NULL — an existing note with a link keeps it (as a one-item
    list) rather than silently losing it."""
    op.add_column(
        "notes", sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.execute(
        """
        UPDATE notes
        SET links = CASE
            WHEN linked_source IS NOT NULL THEN
                jsonb_build_array(
                    jsonb_build_object(
                        'source', linked_source,
                        'url', linked_url,
                        'title', linked_title
                    )
                )
            ELSE '[]'::jsonb
        END
        """
    )
    op.alter_column("notes", "links", nullable=False)
    op.drop_column("notes", "linked_title")
    op.drop_column("notes", "linked_source")
    op.drop_column("notes", "linked_url")


def downgrade() -> None:
    """Inverse backfill: a note's first link (if any) becomes the single
    linked_source/url/title; any second+ link is dropped — the old shape
    genuinely can't hold more than one, there's no lossless way back."""
    op.add_column(
        "notes",
        sa.Column("linked_url", sa.VARCHAR(length=2048), autoincrement=False, nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("linked_source", sa.VARCHAR(length=16), autoincrement=False, nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("linked_title", sa.VARCHAR(length=1024), autoincrement=False, nullable=True),
    )
    op.execute(
        """
        UPDATE notes
        SET
            linked_source = links->0->>'source',
            linked_url = links->0->>'url',
            linked_title = links->0->>'title'
        WHERE jsonb_array_length(links) > 0
        """
    )
    op.drop_column("notes", "links")
