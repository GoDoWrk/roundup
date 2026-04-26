from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.db.session import get_db_session
from app.schemas.search import SearchCounts, SearchResponse, SearchResult
from app.services.clustering import _is_legacy_source_count_validation_error
from app.services.serialization import build_story_cluster

router = APIRouter(prefix="/api/search", tags=["search"])


@dataclass(frozen=True)
class RankedResult:
    rank: int
    last_updated: datetime
    score: float
    cluster_id: str
    item: SearchResult


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(value: str | None, query: str) -> bool:
    return query.casefold() in (value or "").casefold()


def _matched_field(query: str, fields: list[tuple[str, str | None]]) -> str | None:
    for field_name, value in fields:
        if _contains(value, query):
            return field_name
    return None


def _snippet(query: str, fields: list[str | None], fallback: str, max_length: int = 220) -> str:
    source = next((value.strip() for value in fields if _contains(value, query) and value and value.strip()), fallback.strip())
    if len(source) <= max_length:
        return source

    query_index = source.casefold().find(query.casefold())
    if query_index < 0:
        return f"{source[: max_length - 3].rstrip()}..."

    half_window = max_length // 2
    start = max(0, query_index - half_window)
    end = min(len(source), start + max_length)
    start = max(0, end - max_length)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(source) else ""
    return f"{prefix}{source[start:end].strip()}{suffix}"


def _public_cluster_filters(settings):
    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    return (
        Cluster.status != "hidden",
        source_count_subquery >= settings.cluster_min_sources_for_api,
        or_(Cluster.validation_error.is_(None), Cluster.validation_error == legacy_source_count_error),
    )


def _search_filters(pattern: str):
    article_match = (
        select(ClusterArticle.id)
        .join(Article, Article.id == ClusterArticle.article_id)
        .where(
            ClusterArticle.cluster_id == Cluster.id,
            or_(
                Article.title.ilike(pattern, escape="\\"),
                Article.publisher.ilike(pattern, escape="\\"),
                Article.topic.ilike(pattern, escape="\\"),
            ),
        )
        .exists()
    )
    timeline_match = (
        select(ClusterTimelineEvent.id)
        .where(
            ClusterTimelineEvent.cluster_id == Cluster.id,
            or_(
                ClusterTimelineEvent.event.ilike(pattern, escape="\\"),
                ClusterTimelineEvent.source_title.ilike(pattern, escape="\\"),
            ),
        )
        .exists()
    )
    return or_(
        Cluster.headline.ilike(pattern, escape="\\"),
        Cluster.summary.ilike(pattern, escape="\\"),
        Cluster.what_changed.ilike(pattern, escape="\\"),
        Cluster.why_it_matters.ilike(pattern, escape="\\"),
        Cluster.topic.ilike(pattern, escape="\\"),
        article_match,
        timeline_match,
    )


def _cluster_rank(cluster: Cluster, query: str, matched_field: str | None) -> int:
    headline = cluster.headline or ""
    topic = cluster.topic or ""
    if headline.casefold() == query.casefold() or topic.casefold() == query.casefold():
        return 100
    if _contains(headline, query):
        return 92
    if _contains(topic, query):
        return 88
    if matched_field in {"summary", "what_changed", "why_it_matters"}:
        return 72
    return 60


def _update_rank(matched_field: str | None) -> int:
    if matched_field == "what_changed":
        return 82
    if matched_field == "why_it_matters":
        return 78
    return 66


def _source_rank(publisher: str, query: str, matched_field: str | None) -> int:
    if publisher.casefold() == query.casefold():
        return 96
    if matched_field == "publisher":
        return 90
    if matched_field == "title":
        return 74
    return 64


def _result_id(result_type: str, cluster_id: str, suffix: str) -> str:
    return f"{result_type}:{cluster_id}:{suffix}"


def _build_results(cluster: Cluster, query: str) -> list[RankedResult]:
    story = build_story_cluster(cluster)
    thumbnail_url = story.primary_image_url or next(iter(story.thumbnail_urls), None)
    update_count = len(story.timeline_events or story.timeline)
    source_count = story.source_count
    results: list[RankedResult] = []

    cluster_fields = [
        ("headline", cluster.headline),
        ("topic", story.topic),
        ("summary", cluster.summary),
        ("article_title", " ".join(source.title for source in story.sources)),
    ]
    cluster_match = _matched_field(query, cluster_fields)
    if cluster_match is not None:
        item = SearchResult(
            id=_result_id("cluster", cluster.id, "story"),
            type="cluster",
            cluster_id=cluster.id,
            title=cluster.headline,
            snippet=_snippet(query, [cluster.summary, cluster.headline, story.topic], cluster.summary or cluster.headline),
            topic=story.topic,
            thumbnail_url=thumbnail_url,
            source_name=story.sources[0].publisher if story.sources else None,
            source_count=source_count,
            update_count=update_count,
            last_updated=cluster.last_updated,
            matched_field=cluster_match,
        )
        results.append(RankedResult(_cluster_rank(cluster, query, cluster_match), cluster.last_updated, cluster.score, cluster.id, item))

    update_fields = [
        ("what_changed", cluster.what_changed),
        ("why_it_matters", cluster.why_it_matters),
    ]
    update_match = _matched_field(query, update_fields)
    update_title = cluster.headline
    update_snippet_fields: list[str | None] = [cluster.what_changed, cluster.why_it_matters]
    update_time = cluster.last_updated
    if update_match is None:
        for timeline_event in story.timeline_events:
            if _contains(timeline_event.event, query) or _contains(timeline_event.source_title, query):
                update_match = "timeline"
                update_title = timeline_event.event
                update_snippet_fields = [timeline_event.event, timeline_event.source_title]
                update_time = timeline_event.timestamp
                break

    if update_match is not None:
        item = SearchResult(
            id=_result_id("update", cluster.id, update_match),
            type="update",
            cluster_id=cluster.id,
            title=update_title,
            snippet=_snippet(query, update_snippet_fields, cluster.what_changed or cluster.summary or cluster.headline),
            topic=story.topic,
            thumbnail_url=thumbnail_url,
            source_name=story.sources[0].publisher if story.sources else None,
            source_count=source_count,
            update_count=update_count,
            last_updated=update_time,
            matched_field=update_match,
        )
        results.append(RankedResult(_update_rank(update_match), update_time, cluster.score, cluster.id, item))

    for source in story.sources:
        source_match = _matched_field(
            query,
            [
                ("publisher", source.publisher),
                ("title", source.title),
                ("topic", story.topic),
            ],
        )
        if source_match is None:
            continue
        item = SearchResult(
            id=_result_id("source", cluster.id, str(source.article_id)),
            type="source",
            cluster_id=cluster.id,
            title=source.title,
            snippet=_snippet(query, [source.publisher, source.title], source.title),
            topic=story.topic,
            thumbnail_url=source.image_url or thumbnail_url,
            source_name=source.publisher,
            source_count=source_count,
            update_count=update_count,
            last_updated=cluster.last_updated,
            article_url=source.url,
            published_at=source.published_at,
            matched_field=source_match,
        )
        results.append(
            RankedResult(_source_rank(source.publisher, query, source_match), cluster.last_updated, cluster.score, cluster.id, item)
        )

    return results


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> SearchResponse:
    settings = get_settings()
    final_limit = min(limit, settings.api_max_limit)
    query = q.strip()
    if not query:
        return SearchResponse(
            query="",
            total=0,
            limit=final_limit,
            counts=SearchCounts(all=0, clusters=0, updates=0, sources=0),
            items=[],
        )

    pattern = f"%{_escape_like(query)}%"
    stmt = (
        select(Cluster)
        .options(
            selectinload(Cluster.source_links).selectinload(ClusterArticle.article),
            selectinload(Cluster.timeline_events),
        )
        .where(*_public_cluster_filters(settings), _search_filters(pattern))
        .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
        .limit(settings.api_max_limit)
    )
    clusters = list(db.scalars(stmt).unique().all())

    ranked_results: list[RankedResult] = []
    for cluster in clusters:
        if cluster.validation_error is not None and not _is_legacy_source_count_validation_error(cluster.validation_error, settings):
            continue
        ranked_results.extend(_build_results(cluster, query))

    ranked_results.sort(
        key=lambda result: (
            -result.rank,
            -result.score,
            -result.last_updated.timestamp(),
            result.cluster_id,
            result.item.id,
        )
    )
    all_items = [result.item for result in ranked_results]
    counts = SearchCounts(
        all=len(all_items),
        clusters=sum(1 for item in all_items if item.type == "cluster"),
        updates=sum(1 for item in all_items if item.type == "update"),
        sources=sum(1 for item in all_items if item.type == "source"),
    )

    return SearchResponse(
        query=query,
        total=len(all_items),
        limit=final_limit,
        counts=counts,
        items=all_items[:final_limit],
    )
