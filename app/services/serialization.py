from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from app.db.models import Article, Cluster
from app.schemas.article import ArticleDebugItem, ArticleResponse
from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent
from app.services.normalizer import extract_image_url
from app.services.topics import derive_topic_from_article, derive_topic_from_articles

MAX_CLUSTER_THUMBNAILS = 4


def _valid_image_url(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse(parsed._replace(fragment=""))


def _article_image_url(article: Article) -> str | None:
    stored = _valid_image_url(article.image_url)
    if stored is not None:
        return stored
    return _valid_image_url(extract_image_url(article.raw_payload if isinstance(article.raw_payload, dict) else {}, article.content_text))


def _cluster_image_urls(cluster: Cluster) -> list[str]:
    ranked_links = sorted(
        [link for link in cluster.source_links if link.article is not None],
        key=lambda link: (
            link.article.published_at,
            link.similarity_score,
            link.article.id,
        ),
        reverse=True,
    )

    seen: set[str] = set()
    urls: list[str] = []
    for link in ranked_links:
        candidate = _article_image_url(link.article)
        if candidate is None:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(candidate)
        if len(urls) >= MAX_CLUSTER_THUMBNAILS:
            break
    return urls


def article_to_response(article: Article) -> ArticleResponse:
    return ArticleResponse(
        article_id=article.id,
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        published_at=article.published_at,
        image_url=_article_image_url(article),
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
        image_url=_article_image_url(article),
        keywords=list(article.keywords),
        entities=list(article.entities),
        topic=derive_topic_from_article(article),
    )


def build_story_cluster(cluster: Cluster) -> StoryCluster:
    source_links = list(cluster.source_links)
    timeline_rows = list(cluster.timeline_events)
    articles = [link.article for link in source_links if link.article is not None]
    thumbnail_urls = _cluster_image_urls(cluster)

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
            image_url=_article_image_url(article),
        )
        for article in articles
    ]

    return StoryCluster(
        cluster_id=cluster.id,
        headline=cluster.headline,
        topic=derive_topic_from_articles(articles),
        summary=cluster.summary,
        what_changed=cluster.what_changed,
        why_it_matters=cluster.why_it_matters,
        primary_image_url=thumbnail_urls[0] if thumbnail_urls else None,
        thumbnail_urls=thumbnail_urls,
        timeline=timeline,
        sources=sources,
        first_seen=cluster.first_seen,
        last_updated=cluster.last_updated,
        score=cluster.score,
        status=cluster.status,
    )
