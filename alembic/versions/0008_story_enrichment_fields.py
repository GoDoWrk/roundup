"""add persisted story enrichment fields

Revision ID: 0008_story_enrichment_fields
Revises: 0007_article_image_url
Create Date: 2026-04-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008_story_enrichment_fields"
down_revision: Union[str, None] = "0007_article_image_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clusters",
        sa.Column("key_facts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "clusters",
        sa.Column("related_cluster_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("clusters", "key_facts", server_default=None)
    op.alter_column("clusters", "related_cluster_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("clusters", "related_cluster_ids")
    op.drop_column("clusters", "key_facts")
