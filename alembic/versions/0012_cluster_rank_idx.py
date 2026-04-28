"""add cluster ranking index

Revision ID: 0012_cluster_rank_idx
Revises: 0011_db_hygiene_indexes
Create Date: 2026-04-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0012_cluster_rank_idx"
down_revision: Union[str, None] = "0011_db_hygiene_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clusters_score_last_updated "
        "ON clusters (score, last_updated, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clusters_score_last_updated")
