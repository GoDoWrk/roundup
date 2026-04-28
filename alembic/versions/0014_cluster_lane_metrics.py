"""add cluster lane metrics

Revision ID: 0014_cluster_lane_metrics
Revises: 0013_topic_lanes
Create Date: 2026-04-28 15:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0014_cluster_lane_metrics"
down_revision: Union[str, None] = "0013_topic_lanes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


METRIC_COLUMNS = (
    "cluster_candidates_same_topic_total",
    "cluster_candidates_cross_topic_rejected_total",
    "cluster_entity_overlap_attach_total",
    "cluster_entity_conflict_rejected_total",
    "cluster_no_candidate_new_total",
    "cluster_topic_lane_attach_total",
    "cluster_topic_lane_new_total",
)


def upgrade() -> None:
    for column_name in METRIC_COLUMNS:
        op.add_column(
            "pipeline_stats",
            sa.Column(column_name, sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for column_name in reversed(METRIC_COLUMNS):
        op.drop_column("pipeline_stats", column_name)
