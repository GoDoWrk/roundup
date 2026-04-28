from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

from app.db.models import Article, Cluster
from app.schemas.article import ArticleDebugItem, ArticleResponse
from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent
from app.services.content_quality import classify_article_content, evaluate_article_quality
from app.services.enrichment import build_key_facts
from app.services.normalizer import extract_image_url
from app.services.topics import apply_topic_classification, classify_topic_from_article, derive_topic_from_article, derive_topic_from_articles

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
    payload = article.raw_payload if isinstance(article.raw_payload, dict) else {}
    return _valid_image_url(extract_image_url(payload, article.content_text))


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
    topic_classification = apply_topic_classification(article)
    return ArticleResponse(
        article_id=article.id,
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        published_at=article.published_at,
        image_url=_article_image_url(article),
        topic=derive_topic_from_article(article),
        primary_topic=topic_classification.primary_topic,
        subtopic=topic_classification.subtopic,
        key_entities=list(topic_classification.key_entities),
        geography=topic_classification.geography,
        event_type=topic_classification.event_type,
    )


def article_to_debug(article: Article) -> ArticleDebugItem:
    quality = evaluate_article_quality(article)
    raw_payload = article.raw_payload if isinstance(article.raw_payload, dict) else {}
    classification = classify_article_content(
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        content_text=article.content_text,
        raw_payload=raw_payload,
        source_trust=quality.source_trust,
    )
    topic_classification = apply_topic_classification(article)
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
        primary_topic=topic_classification.primary_topic,
        subtopic=topic_classification.subtopic,
        key_entities=list(topic_classification.key_entities),
        geography=topic_classification.geography,
        event_type=topic_classification.event_type,
        quality_action=quality.action,
        quality_reasons=list(quality.reasons),
        source_trust=quality.source_trust,
        source_priority=quality.source_controls.priority,
        allow_service_content=quality.source_controls.allow_service_content,
        promote_to_home=quality.source_controls.promote_to_home,
        source_category=quality.source_controls.category,
        content_class=classification.content_class,
        primary_entities=list(classification.primary_entities),
        secondary_entities=list(classification.secondary_entities),
    )


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


def _story_topic(cluster: Cluster, articles: list[Article]) -> str:
    stored_topic = str(getattr(cluster, "topic", "") or "").strip()
    return stored_topic or derive_topic_from_articles(articles)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_developing(cluster: Cluster, source_count: int) -> bool:
    if cluster.status == "emerging":
        return True
    last_updated = _as_aware_utc(cluster.last_updated)
    return source_count >= 2 and datetime.now(timezone.utc) - last_updated <= timedelta(hours=24)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_story_cluster(
    cluster: Cluster,
    *,
    visibility: str = "public",
    visibility_label: str = "Confirmed",
) -> StoryCluster:
    source_links = list(cluster.source_links)
    articles = sorted(
        (link.article for link in source_links if link.article is not None),
        key=lambda article: (article.published_at, article.id),
        reverse=True,
    )
    timeline_rows = sorted(
        cluster.timeline_events,
        key=lambda row: (row.timestamp, row.id or 0),
        reverse=True,
    )
    thumbnail_urls = _cluster_image_urls(cluster)
    primary_topic = (cluster.primary_topic or "").strip()
    if not primary_topic and articles:
        primary_topic = classify_topic_from_article(articles[0]).primary_topic

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
            image_url=_article_image_url(article),
        )
        for article in articles
    ]

    key_facts = _string_list(getattr(cluster, "key_facts", []))
    if not key_facts:
        key_facts = build_key_facts(cluster.id, articles)

    return StoryCluster(
        cluster_id=cluster.id,
        headline=cluster.headline,
        topic=_story_topic(cluster, articles),
        primary_topic=primary_topic or "U.S.",
        subtopic=cluster.subtopic,
        key_entities=_string_list(getattr(cluster, "key_entities", [])),
        geography=cluster.geography,
        event_type=cluster.event_type,
        summary=cluster.summary,
        what_changed=cluster.what_changed,
        why_it_matters=cluster.why_it_matters,
        key_facts=key_facts,
        timeline=timeline,
        timeline_events=timeline,
        sources=sources,
        source_count=len(sources),
        primary_image_url=thumbnail_urls[0] if thumbnail_urls else None,
        thumbnail_urls=thumbnail_urls,
        region=None,
        story_type="general",
        first_seen=cluster.first_seen,
        last_updated=cluster.last_updated,
        is_developing=_is_developing(cluster, len(sources)),
        is_breaking=False,
        confidence_score=cluster.score,
        related_cluster_ids=_string_list(getattr(cluster, "related_cluster_ids", [])),
        score=cluster.score,
        status=cluster.status,
        visibility=visibility,
        visibility_label=visibility_label,
        is_single_source=len(sources) == 1,
    )
