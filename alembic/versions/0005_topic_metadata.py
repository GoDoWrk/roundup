"""add topic metadata to articles and clusters

Revision ID: 0005_topic_metadata
Revises: 0004_cluster_promo
Create Date: 2026-04-23 22:45:00.000000
"""

from collections import defaultdict
import re
from types import SimpleNamespace
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_topic_metadata"
down_revision: Union[str, None] = "0004_cluster_promo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TOPIC_STOPWORDS = {
    "about",
    "after",
    "also",
    "against",
    "among",
    "because",
    "before",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
    "many",
    "more",
    "most",
    "news",
    "over",
    "said",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "were",
    "with",
    "would",
}


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in _TOPIC_STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:max_keywords]]


def derive_topic_from_text(title: str, content_text: str = "") -> str:
    combined = f"{_normalize_whitespace(title)} {_normalize_whitespace(content_text[:2000])}".strip()
    if not combined:
        return "General"
    keywords = _extract_keywords(combined)
    if len(keywords) >= 2:
        return f"{keywords[0].title()} {keywords[1].title()}"
    if keywords:
        return keywords[0].title()
    fallback_words = [word for word in re.findall(r"[A-Za-z0-9]+", _normalize_whitespace(title)) if len(word) > 2]
    return " ".join(word.title() for word in fallback_words[:2]) or "General"


def derive_topic_from_articles(articles: list[SimpleNamespace]) -> str:
    if not articles:
        return "General"
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, article in enumerate(articles):
        topic = str(getattr(article, "topic", "") or "").strip() or derive_topic_from_text(
            str(getattr(article, "title", "") or ""),
            str(getattr(article, "content_text", "") or ""),
        )
        counts[topic] = counts.get(topic, 0) + 1
        first_seen.setdefault(topic, index)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], first_seen[item[0]], item[0].lower()))
    return ranked[0][0] if ranked else "General"


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
