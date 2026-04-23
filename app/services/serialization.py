from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.schemas.article import ArticleDebugItem, ArticleResponse
from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent


def article_to_response(article: Article) -> ArticleResponse:
    return ArticleResponse(
        article_id=article.id,
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        published_at=article.published_at,
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
    )


def build_story_cluster(session: Session, cluster: Cluster) -> StoryCluster:
    sources_stmt: Select[tuple[Article]] = (
        select(Article)
        .join(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.cluster_id == cluster.id)
        .order_by(Article.published_at.asc(), Article.id.asc())
    )
    articles = list(session.scalars(sources_stmt).all())

    timeline_stmt: Select[tuple[ClusterTimelineEvent]] = (
        select(ClusterTimelineEvent)
        .where(ClusterTimelineEvent.cluster_id == cluster.id)
        .order_by(ClusterTimelineEvent.timestamp.asc(), ClusterTimelineEvent.id.asc())
    )
    timeline_rows = list(session.scalars(timeline_stmt).all())

    timeline = [
        TimelineEvent(
            timestamp=row.timestamp,
            event=row.event,
            source_url=row.source_url,
            source_title=row.source_title,
        )
        for row in timeline_rows
    ]

    sources = [
        SourceReference(
            article_id=article.id,
            title=article.title,
            url=article.url,
            publisher=article.publisher,
            published_at=article.published_at,
        )
        for article in articles
    ]

    return StoryCluster(
        cluster_id=cluster.id,
        headline=cluster.headline,
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
