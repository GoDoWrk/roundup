from __future__ import annotations

from app.db.models import Article, Cluster
from app.schemas.article import ArticleDebugItem, ArticleResponse
from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent
from app.services.topics import derive_topic_from_article, derive_topic_from_articles


def article_to_response(article: Article) -> ArticleResponse:
    return ArticleResponse(
        article_id=article.id,
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        published_at=article.published_at,
        topic=derive_topic_from_article(article),
    )


def article_to_debug(article: Article) -> ArticleDebugItem:
    return ArticleDebugItem(
        article_id=article.id,
        dedupe_hash=article.dedupe_hash,
        title=article.title,
        normalized_title=article.normalized_title,
        publisher=article.publisher,
        published_at=article.published_at,
        keywords=list(article.keywords),
        entities=list(article.entities),
        topic=derive_topic_from_article(article),
    )


def build_story_cluster(cluster: Cluster) -> StoryCluster:
    source_links = list(cluster.source_links)
    timeline_rows = list(cluster.timeline_events)
    articles = [link.article for link in source_links if link.article is not None]

    timeline = [
        TimelineEvent(
            timestamp=row.timestamp,
            event=row.event,
            source_url=row.source_url,
            source_title=row.source_title,
        )
        for row in timeline_rows
    ]

    sources = [SourceReference(article_id=article.id, title=article.title, url=article.url, publisher=article.publisher, published_at=article.published_at) for article in articles]

    return StoryCluster(
        cluster_id=cluster.id,
        headline=cluster.headline,
        topic=derive_topic_from_articles(articles),
        summary=cluster.summary,
        what_changed=cluster.what_changed,
        why_it_matters=cluster.why_it_matters,
        timeline=timeline,
        sources=sources,
        first_seen=cluster.first_seen,
        last_updated=cluster.last_updated,
        score=cluster.score,
        status=cluster.status,
    )
