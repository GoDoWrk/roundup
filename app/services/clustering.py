from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.services.enrichment import (
    build_headline,
    build_status,
    build_summary,
    build_timeline_event_text,
    build_what_changed,
    build_why_it_matters,
)
from app.services.normalizer import normalize_title
from app.services.validation import validate_cluster_record


@dataclass(frozen=True)
class FeatureVector:
    title: str
    keywords: set[str]
    entities: set[str]
    published_at: datetime


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    intersection = len(left.intersection(right))
    union = len(left.union(right))
    if union == 0:
        return 0.0
    return intersection / union


def _title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _time_proximity(article_time: datetime, cluster_time: datetime, window_hours: int) -> float:
    delta_hours = abs((article_time - cluster_time).total_seconds()) / 3600
    if delta_hours >= window_hours:
        return 0.0
    return 1.0 - (delta_hours / max(window_hours, 1))


def compute_similarity(article: FeatureVector, cluster: FeatureVector, window_hours: int) -> float:
    score = 0.0
    score += 0.45 * _title_similarity(article.title, cluster.title)
    score += 0.25 * _jaccard(article.entities, cluster.entities)
    score += 0.20 * _jaccard(article.keywords, cluster.keywords)
    score += 0.10 * _time_proximity(article.published_at, cluster.published_at, window_hours)
    return round(score, 4)


def _article_features(article: Article) -> FeatureVector:
    return FeatureVector(
        title=article.normalized_title,
        keywords=set(article.keywords),
        entities=set(article.entities),
        published_at=article.published_at,
    )


def _cluster_features(cluster: Cluster) -> FeatureVector:
    return FeatureVector(
        title=cluster.normalized_headline,
        keywords=set(cluster.keywords),
        entities=set(cluster.entities),
        published_at=cluster.last_updated,
    )


def _load_unclustered_articles(session: Session) -> list[Article]:
    stmt: Select[tuple[Article]] = (
        select(Article)
        .outerjoin(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.id.is_(None))
        .order_by(Article.published_at.asc(), Article.id.asc())
    )
    return list(session.scalars(stmt).all())


def _load_candidate_clusters(session: Session, article: Article, settings: Settings) -> list[Cluster]:
    threshold_time = article.published_at - timedelta(hours=settings.cluster_time_window_hours)
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .where(Cluster.last_updated >= threshold_time)
        .order_by(Cluster.last_updated.desc())
    )
    return list(session.scalars(stmt).all())


def _rebuild_cluster(session: Session, cluster: Cluster, settings: Settings) -> None:
    articles_stmt: Select[tuple[Article]] = (
        select(Article)
        .join(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.cluster_id == cluster.id)
        .order_by(Article.published_at.asc(), Article.id.asc())
    )
    articles = list(session.scalars(articles_stmt).all())
    if not articles:
        return

    first_seen = min(article.published_at for article in articles)
    last_updated = max(article.published_at for article in articles)

    keyword_union: set[str] = set()
    entity_union: set[str] = set()
    similarity_stmt = select(func.avg(ClusterArticle.similarity_score)).where(ClusterArticle.cluster_id == cluster.id)
    avg_similarity = session.scalar(similarity_stmt) or 0.0

    for article in articles:
        keyword_union.update(article.keywords)
        entity_union.update(article.entities)

    cluster.first_seen = first_seen
    cluster.last_updated = last_updated
    cluster.headline = build_headline(cluster.id, articles)
    cluster.summary = build_summary(cluster.id, articles)
    cluster.what_changed = build_what_changed(cluster.id, articles)
    cluster.why_it_matters = build_why_it_matters(cluster.id, articles)
    cluster.normalized_headline = normalize_title(cluster.headline)
    cluster.keywords = sorted(keyword_union)
    cluster.entities = sorted(entity_union)
    cluster.score = round(float(avg_similarity), 4)
    cluster.status = build_status(
        source_count=len(articles),
        last_updated=last_updated,
        now=datetime.now(timezone.utc),
        stale_hours=settings.cluster_stale_hours,
        emerging_hours=settings.cluster_emerging_hours,
        emerging_source_count=settings.cluster_emerging_source_count,
    )

    session.query(ClusterTimelineEvent).filter(ClusterTimelineEvent.cluster_id == cluster.id).delete()
    for article in articles:
        event = ClusterTimelineEvent(
            cluster_id=cluster.id,
            timestamp=article.published_at,
            event=build_timeline_event_text(article),
            source_url=article.url,
            source_title=article.title,
        )
        session.add(event)

    validation = validate_cluster_record(cluster)
    cluster.validation_error = validation.error


def _attach_article_to_cluster(session: Session, cluster: Cluster, article: Article, score: float) -> None:
    link = ClusterArticle(cluster_id=cluster.id, article_id=article.id, similarity_score=score)
    session.add(link)


def _create_cluster(session: Session, article: Article) -> Cluster:
    cluster = Cluster(
        id=str(uuid.uuid4()),
        headline="pending headline",
        summary="pending summary",
        what_changed="pending change",
        why_it_matters="pending impact",
        first_seen=article.published_at,
        last_updated=article.published_at,
        score=0.0,
        status="emerging",
        normalized_headline=article.normalized_title,
        keywords=article.keywords,
        entities=article.entities,
    )
    session.add(cluster)
    session.flush()
    return cluster


def cluster_new_articles(session: Session, settings: Settings) -> tuple[int, int]:
    created_count = 0
    updated_count = 0
    pending = _load_unclustered_articles(session)

    for article in pending:
        article_features = _article_features(article)
        candidates = _load_candidate_clusters(session, article, settings)

        best_cluster: Cluster | None = None
        best_score = 0.0

        for cluster in candidates:
            cluster_features = _cluster_features(cluster)
            score = compute_similarity(article_features, cluster_features, settings.cluster_time_window_hours)
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is None or best_score < settings.cluster_score_threshold:
            best_cluster = _create_cluster(session, article)
            created_count += 1
            best_score = 1.0

        _attach_article_to_cluster(session, best_cluster, article, best_score)
        _rebuild_cluster(session, best_cluster, settings)
        updated_count += 1

    return created_count, updated_count
