"""cluster quality and observability fields

Revision ID: 0002_cluster_obs
Revises: 0001_initial
Create Date: 2026-04-23 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_cluster_obs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cluster_articles", sa.Column("heuristic_breakdown", sa.JSON(), nullable=True))

    op.add_column("pipeline_stats", sa.Column("cluster_candidates_evaluated_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_signal_rejected_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_attach_decisions_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_new_decisions_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_low_confidence_new_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_validation_rejected_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pipeline_stats", sa.Column("cluster_timeline_events_deduplicated_total", sa.Integer(), nullable=False, server_default="0"))

    op.execute("UPDATE cluster_articles SET heuristic_breakdown='{}' WHERE heuristic_breakdown IS NULL")
    op.alter_column("cluster_articles", "heuristic_breakdown", nullable=False)


def downgrade() -> None:
    op.drop_column("pipeline_stats", "cluster_timeline_events_deduplicated_total")
    op.drop_column("pipeline_stats", "cluster_validation_rejected_total")
    op.drop_column("pipeline_stats", "cluster_low_confidence_new_total")
    op.drop_column("pipeline_stats", "cluster_new_decisions_total")
    op.drop_column("pipeline_stats", "cluster_attach_decisions_total")
    op.drop_column("pipeline_stats", "cluster_signal_rejected_total")
    op.drop_column("pipeline_stats", "cluster_candidates_evaluated_total")
    op.drop_column("cluster_articles", "heuristic_breakdown")
