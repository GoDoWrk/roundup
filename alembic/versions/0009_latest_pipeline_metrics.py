"""add latest pipeline run metrics

Revision ID: 0009_latest_pipeline_metrics
Revises: 0008_story_enrichment_fields
Create Date: 2026-04-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009_latest_pipeline_metrics"
down_revision: Union[str, None] = "0008_story_enrichment_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LATEST_METRIC_COLUMNS = [
    "latest_articles_fetched",
    "latest_articles_stored",
    "latest_duplicate_articles_skipped",
    "latest_articles_malformed",
    "latest_failed_source_count",
    "latest_candidate_clusters_created",
    "latest_clusters_updated",
    "latest_clusters_hidden",
    "latest_clusters_promoted",
    "latest_visible_clusters",
]


def upgrade() -> None:
    for column_name in LATEST_METRIC_COLUMNS:
        op.add_column(
            "pipeline_stats",
            sa.Column(column_name, sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("pipeline_stats", column_name, server_default=None)


def downgrade() -> None:
    for column_name in reversed(LATEST_METRIC_COLUMNS):
        op.drop_column("pipeline_stats", column_name)
