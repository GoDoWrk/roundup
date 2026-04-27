"""add ingestion depth metrics

Revision ID: 0010_ingestion_depth_metrics
Revises: 0009_latest_pipeline_metrics
Create Date: 2026-04-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0010_ingestion_depth_metrics"
down_revision: Union[str, None] = "0009_latest_pipeline_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INGESTION_DEPTH_COLUMNS = [
    "configured_feed_count",
    "active_feed_count",
    "feeds_checked",
    "feeds_with_new_articles",
    "miniflux_entries_seen",
    "articles_fetched_raw",
    "articles_rejected_quality",
    "articles_rejected_stale",
    "articles_rejected_service_finance",
]


def upgrade() -> None:
    for column_name in INGESTION_DEPTH_COLUMNS:
        op.add_column(
            "pipeline_stats",
            sa.Column(column_name, sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("pipeline_stats", column_name, server_default=None)


def downgrade() -> None:
    for column_name in reversed(INGESTION_DEPTH_COLUMNS):
        op.drop_column("pipeline_stats", column_name)
