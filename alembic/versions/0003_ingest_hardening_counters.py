"""add ingest hardening counters

Revision ID: 0003_ingest_hardening_counters
Revises: 0002_cluster_obs
Create Date: 2026-04-23 20:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_ingest_hardening_counters"
down_revision: Union[str, None] = "0002_cluster_obs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_stats",
        sa.Column("articles_malformed_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pipeline_stats",
        sa.Column("ingest_source_failures_total", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pipeline_stats", "ingest_source_failures_total")
    op.drop_column("pipeline_stats", "articles_malformed_total")
