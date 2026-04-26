from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.schemas.article import ArticleDebugItem, ArticleResponse
from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent


IMAGE_FIELD_NAMES = (
    "image",
    "image_url",
    "thumbnail",
    "thumbnail_url",
    "cover_image",
    "cover_image_url",
    "lead_image_url",
)

IMAGE_URL_FIELD_NAMES = ("url", "src", "href")


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


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_from_value(value: object) -> str | None:
    if isinstance(value, str) and _is_http_url(value):
        return value.strip()
    if isinstance(value, dict):
        for field_name in IMAGE_URL_FIELD_NAMES:
            candidate = value.get(field_name)
            if isinstance(candidate, str) and _is_http_url(candidate):
                return candidate.strip()
    return None


def _looks_like_image_enclosure(value: dict) -> bool:
    for field_name in ("mime_type", "content_type", "type"):
        mime_type = value.get(field_name)
        if isinstance(mime_type, str) and mime_type.lower().startswith("image/"):
            return True
    url = _url_from_value(value)
    return bool(url and urlparse(url).path.lower().endswith((".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp")))


def _append_unique(urls: list[str], candidate: str | None) -> None:
    if candidate and candidate not in urls:
        urls.append(candidate)


def _extract_image_urls_from_payload(raw_payload: object) -> list[str]:
    if not isinstance(raw_payload, dict):
        return []

    urls: list[str] = []
    for field_name in IMAGE_FIELD_NAMES:
        value = raw_payload.get(field_name)
        if isinstance(value, list):
            for item in value:
                _append_unique(urls, _url_from_value(item))
        else:
            _append_unique(urls, _url_from_value(value))

    for field_name in ("enclosure", "enclosures"):
        value = raw_payload.get(field_name)
        enclosure_items = value if isinstance(value, list) else [value]
        for item in enclosure_items:
            if isinstance(item, dict) and _looks_like_image_enclosure(item):
                _append_unique(urls, _url_from_value(item))

    media_thumbnail = raw_payload.get("media_thumbnail")
    if isinstance(media_thumbnail, list):
        for item in media_thumbnail:
            _append_unique(urls, _url_from_value(item))

    return urls


def _extract_story_image_urls(articles: list[Article]) -> list[str]:
    urls: list[str] = []
    for article in articles:
        for image_url in _extract_image_urls_from_payload(article.raw_payload):
            _append_unique(urls, image_url)
    return urls


def _timeline_from_articles(articles: list[Article]) -> list[TimelineEvent]:
    return [
        TimelineEvent(
            timestamp=article.published_at,
            event=f"{article.publisher} published: {article.title}",
            source_url=article.url,
            source_title=article.title,
        )
        for article in articles
    ]


def _topic_from_cluster(cluster: Cluster) -> str:
    for value in list(cluster.keywords or []) + list(cluster.entities or []):
        topic = str(value).strip()
        if topic:
            return topic
    return "general"


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_developing(cluster: Cluster, source_count: int) -> bool:
    if cluster.status == "emerging":
        return True
    last_updated = _as_aware_utc(cluster.last_updated)
    return source_count >= 2 and datetime.now(timezone.utc) - last_updated <= timedelta(hours=24)


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
    if not timeline:
        timeline = _timeline_from_articles(articles)

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
    image_urls = _extract_story_image_urls(articles)

    return StoryCluster(
        cluster_id=cluster.id,
        headline=cluster.headline,
        summary=cluster.summary,
        what_changed=cluster.what_changed,
        why_it_matters=cluster.why_it_matters,
        key_facts=[],
        timeline=timeline,
        timeline_events=timeline,
        sources=sources,
        source_count=len(sources),
        primary_image_url=image_urls[0] if image_urls else None,
        thumbnail_urls=image_urls,
        topic=_topic_from_cluster(cluster),
        region=None,
        story_type="general",
        first_seen=cluster.first_seen,
        last_updated=cluster.last_updated,
        is_developing=_is_developing(cluster, len(sources)),
        is_breaking=False,
        confidence_score=cluster.score,
        related_cluster_ids=[],
        score=cluster.score,
        status=cluster.status,
    )
