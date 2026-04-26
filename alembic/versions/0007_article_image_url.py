"""add article image url

Revision ID: 0007_article_image_url
Revises: 0006_article_src_idx_hardening
Create Date: 2026-04-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services.normalizer import extract_image_url


# revision identifiers, used by Alembic.
revision: str = "0007_article_image_url"
down_revision: Union[str, None] = "0006_article_src_idx_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("image_url", sa.Text(), nullable=True))

    bind = op.get_bind()
    articles = sa.table(
        "articles",
        sa.column("id", sa.Integer),
        sa.column("raw_payload", sa.JSON),
        sa.column("content_text", sa.Text),
        sa.column("image_url", sa.Text),
    )
    rows = list(bind.execute(sa.select(articles.c.id, articles.c.raw_payload, articles.c.content_text)).all())
    for row in rows:
        raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        image_url = extract_image_url(raw_payload, str(row.content_text or ""))
        if image_url is not None:
            bind.execute(articles.update().where(articles.c.id == row.id).values(image_url=image_url))


def downgrade() -> None:
    op.drop_column("articles", "image_url")
