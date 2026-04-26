"""add topic metadata to articles and clusters

Revision ID: 0005_topic_metadata
Revises: 0004_cluster_promo
Create Date: 2026-04-23 22:45:00.000000
"""

from collections import defaultdict
from types import SimpleNamespace
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services.topics import derive_topic_from_articles, derive_topic_from_text


# revision identifiers, used by Alembic.
revision: str = "0005_topic_metadata"
down_revision: Union[str, None] = "0004_cluster_promo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("topic", sa.Text(), nullable=False, server_default=""))
    op.add_column("clusters", sa.Column("topic", sa.Text(), nullable=False, server_default=""))
    op.create_index("ix_articles_topic", "articles", ["topic"], unique=False)
    op.create_index("ix_clusters_topic", "clusters", ["topic"], unique=False)

    bind = op.get_bind()

    articles = sa.table(
        "articles",
        sa.column("id", sa.Integer),
        sa.column("title", sa.Text),
        sa.column("content_text", sa.Text),
        sa.column("topic", sa.Text),
    )
    article_rows = list(bind.execute(sa.select(articles.c.id, articles.c.title, articles.c.content_text)).all())
    for row in article_rows:
        topic = derive_topic_from_text(str(row.title or ""), str(row.content_text or ""))
        bind.execute(articles.update().where(articles.c.id == row.id).values(topic=topic))

    cluster_articles = sa.table(
        "cluster_articles",
        sa.column("cluster_id", sa.String(length=64)),
        sa.column("article_id", sa.Integer),
    )
    cluster_rows = sa.table(
        "clusters",
        sa.column("id", sa.String(length=64)),
        sa.column("topic", sa.Text),
    )

    joined = sa.select(
        cluster_articles.c.cluster_id,
        articles.c.title,
        articles.c.content_text,
        articles.c.topic,
    ).select_from(
        cluster_articles.join(articles, cluster_articles.c.article_id == articles.c.id)
    )
    grouped_articles: dict[str, list[SimpleNamespace]] = defaultdict(list)
    for row in bind.execute(joined).all():
        grouped_articles[str(row.cluster_id)].append(
            SimpleNamespace(title=row.title, content_text=row.content_text, topic=row.topic)
        )

    for cluster_id, items in grouped_articles.items():
        topic = derive_topic_from_articles(items)
        bind.execute(cluster_rows.update().where(cluster_rows.c.id == cluster_id).values(topic=topic))

def downgrade() -> None:
    op.drop_index("ix_clusters_topic", table_name="clusters")
    op.drop_index("ix_articles_topic", table_name="articles")
    op.drop_column("clusters", "topic")
    op.drop_column("articles", "topic")
