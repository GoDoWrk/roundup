"""add controlled topic lane metadata

Revision ID: 0013_topic_lanes
Revises: 0012_cluster_rank_idx
Create Date: 2026-04-28 12:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0013_topic_lanes"
down_revision: Union[str, None] = "0012_cluster_rank_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_empty_list_default() -> sa.TextClause:
    return sa.text("'[]'")


def upgrade() -> None:
    op.add_column("articles", sa.Column("primary_topic", sa.String(length=32), nullable=False, server_default="U.S."))
    op.add_column("articles", sa.Column("subtopic", sa.String(length=64), nullable=True))
    op.add_column("articles", sa.Column("key_entities", sa.JSON(), nullable=False, server_default=_json_empty_list_default()))
    op.add_column("articles", sa.Column("geography", sa.String(length=64), nullable=True))
    op.add_column("articles", sa.Column("event_type", sa.String(length=64), nullable=True))
    op.create_index("ix_articles_primary_subtopic", "articles", ["primary_topic", "subtopic"], unique=False)

    op.add_column("clusters", sa.Column("primary_topic", sa.String(length=32), nullable=False, server_default="U.S."))
    op.add_column("clusters", sa.Column("subtopic", sa.String(length=64), nullable=True))
    op.add_column("clusters", sa.Column("key_entities", sa.JSON(), nullable=False, server_default=_json_empty_list_default()))
    op.add_column("clusters", sa.Column("geography", sa.String(length=64), nullable=True))
    op.add_column("clusters", sa.Column("event_type", sa.String(length=64), nullable=True))
    op.create_index("ix_clusters_primary_subtopic", "clusters", ["primary_topic", "subtopic"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clusters_primary_subtopic", table_name="clusters")
    op.drop_column("clusters", "event_type")
    op.drop_column("clusters", "geography")
    op.drop_column("clusters", "key_entities")
    op.drop_column("clusters", "subtopic")
    op.drop_column("clusters", "primary_topic")

    op.drop_index("ix_articles_primary_subtopic", table_name="articles")
    op.drop_column("articles", "event_type")
    op.drop_column("articles", "geography")
    op.drop_column("articles", "key_entities")
    op.drop_column("articles", "subtopic")
    op.drop_column("articles", "primary_topic")
