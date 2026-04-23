"""add cluster promotion lifecycle fields

Revision ID: 0004_cluster_promo
Revises: 0003_ingest_hardening_counters
Create Date: 2026-04-23 22:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_cluster_promo"
down_revision: Union[str, None] = "0003_ingest_hardening_counters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clusters", sa.Column("previous_status", sa.String(length=32), nullable=True))
    op.add_column("clusters", sa.Column("promotion_reason", sa.Text(), nullable=True))
    op.add_column("clusters", sa.Column("promotion_explanation", sa.Text(), nullable=True))

    op.add_column(
        "pipeline_stats",
        sa.Column("clusters_promoted_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_stats",
        sa.Column("clusters_hidden_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_stats",
        sa.Column("clusters_active_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_stats",
        sa.Column("cluster_promotion_attempts_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_stats",
        sa.Column("cluster_promotion_failures_total", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pipeline_stats", "cluster_promotion_failures_total")
    op.drop_column("pipeline_stats", "cluster_promotion_attempts_total")
    op.drop_column("pipeline_stats", "clusters_active_total")
    op.drop_column("pipeline_stats", "clusters_hidden_total")
    op.drop_column("pipeline_stats", "clusters_promoted_total")

    op.drop_column("clusters", "promotion_explanation")
    op.drop_column("clusters", "promotion_reason")
    op.drop_column("clusters", "previous_status")
    op.drop_column("clusters", "promoted_at")
