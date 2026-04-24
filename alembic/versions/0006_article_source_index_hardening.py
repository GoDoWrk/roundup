"""add article publisher index for source lookups

Revision ID: 0006_article_source_index_hardening
Revises: 0005_topic_metadata
Create Date: 2026-04-24 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0006_article_source_index_hardening"
down_revision: Union[str, None] = "0005_topic_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_publisher ON articles (publisher)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_articles_publisher")
