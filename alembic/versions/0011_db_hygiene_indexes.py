"""add query path indexes

Revision ID: 0011_db_hygiene_indexes
Revises: 0010_ingestion_depth_metrics
Create Date: 2026-04-27 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0011_db_hygiene_indexes"
down_revision: Union[str, None] = "0010_ingestion_depth_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_published_id ON articles (published_at, id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_fetched_id ON articles (fetched_at, id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clusters_last_updated_id ON clusters (last_updated, id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clusters_status_last_updated ON clusters (status, last_updated, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clusters_status_last_updated")
    op.execute("DROP INDEX IF EXISTS ix_clusters_last_updated_id")
    op.execute("DROP INDEX IF EXISTS ix_articles_fetched_id")
    op.execute("DROP INDEX IF EXISTS ix_articles_published_id")
