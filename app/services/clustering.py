from __future__ import annotations

import json
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.services.enrichment import (
    build_headline,
    build_key_facts,
    build_status,
    build_summary,
    build_timeline_events,
    build_what_changed,
    build_why_it_matters,
)
from app.services.normalizer import normalize_title
from app.services.topics import derive_topic_from_article, derive_topic_from_articles, topic_matches
from app.services.validation import validate_cluster_record

logger = logging.getLogger(__name__)

CLUSTER_KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "blank",
    "but",
    "by",
    "com",
    "continue",
    "for",
    "from",
    "get",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "href",
    "https",
    "in",
    "into",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "our",
    "said",
    "says",
    "she",
    "that",
    "the",
    "their",
    "they",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "you",
    "your",
}

CLUSTER_GENERIC_NEWS_TERMS = {
    "attack",
    "attacks",
    "breaking",
    "ceasefire",
    "conflict",
    "crisis",
    "details",
    "developing",
    "latest",
    "live",
    "minister",
    "new",
    "reported",
    "reporting",
    "reports",
    "story",
    "update",
    "updates",
    "war",
}

LOCATION_TERMS = {
    "gaza",
    "iran",
    "israel",
    "lebanon",
    "mali",
    "sahel",
    "syria",
    "ukraine",
    "yemen",
}


@dataclass(frozen=True)
class FeatureVector:
    title: str
    keywords: set[str]
    entities: set[str]
    locations: set[str]
    title_tokens: set[str]
    topic: str
    published_at: datetime
    publishers: set[str]


@dataclass(frozen=True)
class CandidateEvaluation:
    cluster: Cluster
    title_similarity: float
    entity_jaccard: float
    keyword_jaccard: float
    semantic_score: float
    time_proximity: float
    entity_overlap: int
    keyword_overlap: int
    location_overlap: int
    source_match: bool
    topic_match: bool
    score: float
    signal_gate_passed: bool
    signal_reasons: tuple[str, ...]
    rejection_reason: str | None


@dataclass(frozen=True)
class RebuildResult:
    validation_failed: bool
    timeline_deduplicated: int
    promotion_attempted: bool
    promoted: bool
    promotion_failed: bool
    source_count: int
    status: str


@dataclass
class ClusteringRunResult:
    created_count: int
    updated_count: int
    candidates_evaluated: int
    signal_rejected: int
    attach_decisions: int
    new_decisions: int
    low_confidence_new: int
    validation_rejected: int
    timeline_deduplicated: int
    promoted_count: int
    hidden_total: int
    active_total: int
    promotion_attempts: int
    promotion_failures: int


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


def _semantic_score(title_similarity: float, entity_jaccard: float, keyword_jaccard: float) -> float:
    return 0.50 * title_similarity + 0.30 * entity_jaccard + 0.20 * keyword_jaccard


def _tokenize_text(value: str) -> set[str]:
    return {token.strip().lower() for token in (value or "").replace("/", " ").replace("-", " ").split() if token.strip()}


def _semantic_keywords(values: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    keywords: set[str] = set()
    for value in values or []:
        keyword = str(value).strip().lower()
        if keyword and keyword not in CLUSTER_KEYWORD_STOPWORDS and keyword not in CLUSTER_GENERIC_NEWS_TERMS:
            keywords.add(keyword)
    return keywords


def _semantic_entities(values: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    return {entity.lower() for entity in (str(value).strip() for value in values or []) if entity}


def _semantic_locations(*, title: str, keywords: set[str], entities: set[str]) -> set[str]:
    title_tokens = _tokenize_text(title)
    candidates = title_tokens.union(keywords).union(_tokenize_text(" ".join(entities)))
    return {token for token in candidates if token in LOCATION_TERMS}


def _title_signature_tokens(title: str) -> set[str]:
    return {
        token
        for token in _tokenize_text(title)
        if len(token) > 3 and token not in CLUSTER_KEYWORD_STOPWORDS and token not in CLUSTER_GENERIC_NEWS_TERMS
    }


def _article_features(article: Article) -> FeatureVector:
    keywords = _semantic_keywords(article.keywords)
    entities = _semantic_entities(article.entities)
    return FeatureVector(
        title=article.normalized_title,
        keywords=keywords,
        entities=entities,
        locations=_semantic_locations(title=article.title or article.normalized_title, keywords=keywords, entities=entities),
        title_tokens=_title_signature_tokens(article.normalized_title),
        topic=derive_topic_from_article(article),
        published_at=article.published_at,
        publishers={(article.publisher or "").strip().lower()} if (article.publisher or "").strip() else set(),
    )


def _cluster_features(cluster: Cluster) -> FeatureVector:
    cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))
    keywords = _semantic_keywords(cluster.keywords)
    entities = _semantic_entities(cluster.entities)
    publishers = {
        (link.article.publisher or "").strip().lower()
        for link in cluster.source_links
        if link.article is not None and (link.article.publisher or "").strip()
    }
    return FeatureVector(
        title=cluster.normalized_headline,
        keywords=keywords,
        entities=entities,
        locations=_semantic_locations(title=cluster.headline or cluster.normalized_headline, keywords=keywords, entities=entities),
        title_tokens=_title_signature_tokens(cluster.normalized_headline),
        topic=cluster_topic,
        published_at=cluster.last_updated,
        publishers=publishers,
    )


def _evaluate_candidate(
    cluster: Cluster,
    article: FeatureVector,
    cluster_features: FeatureVector,
    settings: Settings,
) -> CandidateEvaluation:
    title_similarity = _title_similarity(article.title, cluster_features.title)
    entity_jaccard = _jaccard(article.entities, cluster_features.entities)
    keyword_jaccard = _jaccard(article.keywords, cluster_features.keywords)
    semantic_score = _semantic_score(title_similarity, entity_jaccard, keyword_jaccard)
    time_proximity = _time_proximity(article.published_at, cluster_features.published_at, settings.cluster_time_window_hours)
    topic_match = topic_matches(article.topic, cluster_features.topic)

    entity_overlap = len(article.entities.intersection(cluster_features.entities))
    keyword_overlap = len(article.keywords.intersection(cluster_features.keywords))
    location_overlap = len(article.locations.intersection(cluster_features.locations))
    source_match = bool(article.publishers.intersection(cluster_features.publishers))
    shared_title_tokens = article.title_tokens.intersection(cluster_features.title_tokens)
    generic_only_keyword_overlap = keyword_overlap > 0 and not (
        article.keywords.intersection(cluster_features.keywords) - CLUSTER_GENERIC_NEWS_TERMS
    )

    score = round(
        0.45 * title_similarity
        + 0.25 * entity_jaccard
        + 0.20 * keyword_jaccard
        + 0.10 * time_proximity,
        4,
    )

    signal_reasons: list[str] = []
    if title_similarity >= settings.cluster_min_title_signal:
        signal_reasons.append("strong_title_similarity")
    if entity_overlap >= settings.cluster_min_entity_overlap:
        signal_reasons.append("meaningful_entity_overlap")
    if keyword_overlap >= settings.cluster_min_keyword_overlap:
        signal_reasons.append("meaningful_keyword_overlap")
    if location_overlap > 0:
        signal_reasons.append("location_overlap")
    if topic_match and semantic_score >= settings.cluster_min_topic_semantic_score:
        signal_reasons.append("topic_semantic_similarity")
    if (
        topic_match
        and title_similarity >= settings.cluster_attach_override_min_title_similarity
        and keyword_overlap > 0
    ):
        signal_reasons.append("topic_title_keyword_similarity")

    semantic_backstop = (
        entity_overlap >= max(2, settings.cluster_min_entity_overlap + 1)
        or (entity_overlap >= settings.cluster_min_entity_overlap and location_overlap > 0)
    ) and title_similarity >= settings.cluster_attach_override_min_title_similarity
    signal_gate_passed = bool(signal_reasons) and (topic_match or semantic_backstop)
    if article.locations and cluster_features.locations and location_overlap == 0 and entity_overlap == 0:
        signal_gate_passed = False
        rejection_reason = "location_conflict_without_entity_overlap"
    elif len(article.title_tokens) >= 2 and len(cluster_features.title_tokens) >= 2 and not shared_title_tokens and entity_overlap == 0:
        signal_gate_passed = False
        rejection_reason = "distinct_event_signatures"
    elif generic_only_keyword_overlap and entity_overlap == 0 and title_similarity < settings.cluster_min_title_signal:
        signal_gate_passed = False
        rejection_reason = "generic_keyword_only_overlap"
    elif not topic_match and not semantic_backstop:
        rejection_reason = "topic_mismatch"
    elif not signal_reasons:
        rejection_reason = "weak_semantic_signals"
    else:
        rejection_reason = None

    return CandidateEvaluation(
        cluster=cluster,
        title_similarity=round(title_similarity, 4),
        entity_jaccard=round(entity_jaccard, 4),
        keyword_jaccard=round(keyword_jaccard, 4),
        semantic_score=round(semantic_score, 4),
        time_proximity=round(time_proximity, 4),
        entity_overlap=entity_overlap,
        keyword_overlap=keyword_overlap,
        location_overlap=location_overlap,
        source_match=source_match,
        topic_match=topic_match,
        score=score,
        signal_gate_passed=signal_gate_passed,
        signal_reasons=tuple(signal_reasons),
        rejection_reason=rejection_reason,
    )


def _is_better_candidate(candidate: CandidateEvaluation, incumbent: CandidateEvaluation | None, epsilon: float) -> bool:
    if incumbent is None:
        return True

    if candidate.score > incumbent.score + epsilon:
        return True
    if incumbent.score > candidate.score + epsilon:
        return False

    candidate_rank = (candidate.entity_overlap, candidate.keyword_overlap, candidate.cluster.last_updated, candidate.cluster.id)
    incumbent_rank = (incumbent.entity_overlap, incumbent.keyword_overlap, incumbent.cluster.last_updated, incumbent.cluster.id)
    return candidate_rank > incumbent_rank


def _load_unclustered_articles(session: Session, limit: int) -> list[Article]:
    stmt: Select[tuple[Article]] = (
        select(Article)
        .outerjoin(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.id.is_(None))
        .order_by(Article.published_at.asc(), Article.id.asc())
        .limit(limit)
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


def _is_legacy_source_count_validation_error(validation_error: str | None, settings: Settings) -> bool:
    if not validation_error:
        return False
    legacy_message = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    return validation_error == legacy_message


def _load_repromotable_hidden_clusters(session: Session, settings: Settings) -> list[Cluster]:
    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .where(
            Cluster.status == "hidden",
            source_count_subquery >= settings.cluster_min_sources_for_api,
            (Cluster.validation_error.is_(None) | (Cluster.validation_error == legacy_source_count_error)),
        )
        .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
    )
    return list(session.scalars(stmt).all())


def _promotion_blockers(
    *,
    source_count: int,
    validation_error: str | None,
    settings: Settings,
) -> list[str]:
    blockers: list[str] = []

    if source_count < settings.cluster_min_sources_for_api:
        blockers.append(
            f"source_count_below_threshold: needs at least {settings.cluster_min_sources_for_api} sources, has {source_count}"
        )

    if validation_error and not _is_legacy_source_count_validation_error(validation_error, settings):
        blockers.append(f"validation_failed: {validation_error}")

    return blockers


def _source_count_subquery():
    return (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )


def _normalized_topic(value: str | None) -> str:
    return (value or "").strip().lower()


def _has_related_topic(left: Cluster, right: Cluster) -> bool:
    left_topic = _normalized_topic(left.topic)
    right_topic = _normalized_topic(right.topic)
    if not left_topic or not right_topic or left_topic == "general" or right_topic == "general":
        return False
    return topic_matches(left.topic, right.topic)


def _related_score(left: Cluster, right: Cluster, settings: Settings) -> tuple[int, int, int, datetime, str] | None:
    left_entities = _semantic_entities(left.entities)
    right_entities = _semantic_entities(right.entities)
    left_keywords = _semantic_keywords(left.keywords)
    right_keywords = _semantic_keywords(right.keywords)
    entity_overlap = len(left_entities.intersection(right_entities))
    keyword_overlap = len(left_keywords.intersection(right_keywords))
    topic_match = _has_related_topic(left, right)

    if not topic_match and entity_overlap == 0 and keyword_overlap < settings.cluster_min_keyword_overlap:
        return None

    score = int(topic_match) * 4 + entity_overlap * 3 + keyword_overlap
    return (score, entity_overlap, keyword_overlap, right.last_updated, right.id)


def _refresh_related_clusters(session: Session, settings: Settings) -> None:
    source_count = _source_count_subquery()
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    clusters = list(
        session.scalars(
            select(Cluster)
            .where(
                Cluster.status != "hidden",
                source_count >= settings.cluster_min_sources_for_api,
                (Cluster.validation_error.is_(None) | (Cluster.validation_error == legacy_source_count_error)),
            )
            .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
        ).all()
    )

    for cluster in clusters:
        ranked: list[tuple[tuple[int, int, int, datetime, str], str]] = []
        for candidate in clusters:
            if candidate.id == cluster.id:
                continue
            score = _related_score(cluster, candidate, settings)
            if score is None:
                continue
            ranked.append((score, candidate.id))

        ranked.sort(reverse=True)
        cluster.related_cluster_ids = [cluster_id for _, cluster_id in ranked[:4]]


def _build_heuristic_breakdown(
    *,
    decision: str,
    decision_reason: str,
    candidate_count: int,
    settings: Settings,
    evaluation: CandidateEvaluation | None,
    attach_override_met: bool = False,
    attach_override_components: dict[str, float | int | bool] | None = None,
) -> dict:
    if evaluation is None:
        components = {
            "title_similarity": 0.0,
            "entity_jaccard": 0.0,
            "keyword_jaccard": 0.0,
            "semantic_score": 0.0,
            "time_proximity": 0.0,
        }
        overlap_counts = {
            "entity_overlap": 0,
            "keyword_overlap": 0,
            "location_overlap": 0,
        }
        selected_score = 0.0
        selected_cluster_id = None
        signal_gate_passed = False
        signal_reasons: tuple[str, ...] = ()
        candidate_rejection_reason = None
    else:
        components = {
            "title_similarity": evaluation.title_similarity,
            "entity_jaccard": evaluation.entity_jaccard,
            "keyword_jaccard": evaluation.keyword_jaccard,
            "semantic_score": evaluation.semantic_score,
            "time_proximity": evaluation.time_proximity,
        }
        overlap_counts = {
            "entity_overlap": evaluation.entity_overlap,
            "keyword_overlap": evaluation.keyword_overlap,
            "location_overlap": evaluation.location_overlap,
        }
        selected_score = evaluation.score
        selected_cluster_id = evaluation.cluster.id
        signal_gate_passed = evaluation.signal_gate_passed
        signal_reasons = evaluation.signal_reasons
        candidate_rejection_reason = evaluation.rejection_reason

    topic_match = evaluation.topic_match if evaluation is not None else False
    selected_topic = evaluation.cluster.topic if evaluation is not None else None
    thresholds = {
        "score_threshold": settings.cluster_score_threshold,
        "title_signal_threshold": settings.cluster_min_title_signal,
        "entity_overlap_threshold": settings.cluster_min_entity_overlap,
        "keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
        "topic_semantic_score_threshold": settings.cluster_min_topic_semantic_score,
        "attach_override_title_similarity_threshold": settings.cluster_attach_override_min_title_similarity,
        "attach_override_time_proximity_threshold": settings.cluster_attach_override_min_time_proximity,
        "attach_override_keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
    }

    thresholds_met = {
        "score_threshold_met": selected_score >= settings.cluster_score_threshold,
        "title_signal_met": components["title_similarity"] >= settings.cluster_min_title_signal,
        "entity_overlap_met": overlap_counts["entity_overlap"] >= settings.cluster_min_entity_overlap,
        "keyword_overlap_met": overlap_counts["keyword_overlap"] >= settings.cluster_min_keyword_overlap,
        "topic_semantic_score_met": topic_match
        and components["semantic_score"] >= settings.cluster_min_topic_semantic_score,
        "topic_match_met": topic_match,
        "signal_gate_passed": signal_gate_passed,
        "attach_override_met": attach_override_met,
    }

    score_formula = "0.45*title_similarity + 0.25*entity_jaccard + 0.20*keyword_jaccard + 0.10*time_proximity"
    semantic_formula = "0.50*title_similarity + 0.30*entity_jaccard + 0.20*keyword_jaccard"

    warnings: list[str] = []
    if decision == "attach_existing_cluster":
        if not signal_gate_passed:
            warnings.append("attached_without_semantic_gate")
        if selected_score < settings.cluster_score_threshold:
            warnings.append("attached_below_score_threshold")
        if components["time_proximity"] >= settings.cluster_attach_override_min_time_proximity and not signal_reasons:
            warnings.append("time_proximity_without_semantic_signal")
        if components["semantic_score"] < settings.cluster_min_topic_semantic_score and not (
            thresholds_met["title_signal_met"]
            or thresholds_met["entity_overlap_met"]
            or thresholds_met["keyword_overlap_met"]
        ):
            warnings.append("low_semantic_score")

    return {
        "decision": decision,
        "decision_reason": decision_reason,
        "candidate_count": candidate_count,
        "selected_cluster_id": selected_cluster_id,
        "selected_topic": selected_topic,
        "selected_score": round(selected_score, 4),
        "selected_topic_match": topic_match,
        "selected_source_match": evaluation.source_match if evaluation is not None else False,
        "score_formula": score_formula,
        "semantic_formula": semantic_formula,
        "components": components,
        "overlap_counts": overlap_counts,
        "thresholds": thresholds,
        "thresholds_met": thresholds_met,
        "signal_reasons": list(signal_reasons),
        "candidate_rejection_reason": candidate_rejection_reason,
        "warnings": warnings,
        "attach_override_components": attach_override_components or {},
    }


def _rebuild_cluster(session: Session, cluster: Cluster, settings: Settings) -> RebuildResult:
    articles_stmt: Select[tuple[Article]] = (
        select(Article)
        .join(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.cluster_id == cluster.id)
        .order_by(Article.published_at.asc(), Article.id.asc())
    )
    articles = list(session.scalars(articles_stmt).all())
    if not articles:
        cluster.status = "hidden"
        cluster.validation_error = "cluster has no source articles"
        cluster.promotion_reason = "no_sources_available"
        cluster.promotion_explanation = "Cluster was hidden because it no longer has any attached source articles."
        cluster.topic = "General"
        return RebuildResult(
            validation_failed=True,
            timeline_deduplicated=0,
            promotion_attempted=False,
            promoted=False,
            promotion_failed=False,
            source_count=0,
            status="hidden",
        )

    first_seen = min(article.published_at for article in articles)
    last_updated = max(article.published_at for article in articles)
    source_count = len(articles)
    previous_status = cluster.status
    promotion_attempted = previous_status == "hidden"

    keyword_union: set[str] = set()
    entity_union: set[str] = set()
    cluster_topics = derive_topic_from_articles(articles)
    similarity_stmt = select(func.avg(ClusterArticle.similarity_score)).where(ClusterArticle.cluster_id == cluster.id)
    avg_similarity = session.scalar(similarity_stmt) or 0.0

    for article in articles:
        keyword_union.update(_semantic_keywords(article.keywords))
        entity_union.update(_semantic_entities(article.entities))

    cluster.first_seen = first_seen
    cluster.last_updated = last_updated
    cluster.headline = build_headline(cluster.id, articles)
    cluster.summary = build_summary(cluster.id, articles)
    cluster.what_changed = build_what_changed(cluster.id, articles)
    cluster.why_it_matters = build_why_it_matters(cluster.id, articles)
    cluster.key_facts = build_key_facts(cluster.id, articles)
    cluster.normalized_headline = normalize_title(cluster.headline)
    cluster.keywords = sorted(keyword_union)
    cluster.entities = sorted(entity_union)
    cluster.topic = cluster_topics
    cluster.score = round(float(avg_similarity), 4)
    cluster.status = build_status(
        source_count=source_count,
        last_updated=last_updated,
        now=datetime.now(timezone.utc),
        stale_hours=settings.cluster_stale_hours,
        emerging_hours=settings.cluster_emerging_hours,
        emerging_source_count=settings.cluster_emerging_source_count,
    )

    timeline_entries, dedup_count = build_timeline_events(
        articles,
        dedupe_window_hours=settings.timeline_dedupe_window_hours,
        dedupe_title_similarity=settings.timeline_dedupe_title_similarity,
    )

    session.query(ClusterTimelineEvent).filter(ClusterTimelineEvent.cluster_id == cluster.id).delete()
    for item in timeline_entries:
        event = ClusterTimelineEvent(
            cluster_id=cluster.id,
            timestamp=item.timestamp,
            event=item.event,
            source_url=item.source_url,
            source_title=item.source_title,
        )
        session.add(event)

    validation = validate_cluster_record(
        cluster,
        source_count=source_count,
        min_sources=settings.cluster_min_sources_for_api,
        min_headline_words=settings.cluster_min_headline_words,
        min_detail_words=settings.cluster_min_detail_words,
    )
    cluster.validation_error = validation.error

    promoted = False
    promotion_failed = False
    promotion_blockers = _promotion_blockers(
        source_count=source_count,
        validation_error=cluster.validation_error,
        settings=settings,
    )
    visibility_eligible = not promotion_blockers
    if visibility_eligible:
        if previous_status == "hidden":
            promoted = True
            cluster.previous_status = previous_status
            cluster.promoted_at = datetime.now(timezone.utc)
            cluster.promotion_reason = "source_count_threshold_reached_and_validation_passed"
            cluster.promotion_explanation = (
                f"Promoted after reaching {source_count} sources and passing validation."
            )
    else:
        cluster.previous_status = previous_status
        cluster.status = "hidden"
        cluster.promotion_reason = "; ".join(blocker.split(":", 1)[0] for blocker in promotion_blockers)
        cluster.promotion_explanation = (
            "Cluster remains hidden until it clears these blockers: "
            + "; ".join(promotion_blockers)
        )
        if promotion_attempted:
            promotion_failed = True

    return RebuildResult(
        validation_failed=not validation.is_valid,
        timeline_deduplicated=dedup_count,
        promotion_attempted=promotion_attempted,
        promoted=promoted,
        promotion_failed=promotion_failed,
        source_count=source_count,
        status=cluster.status,
    )


def _attach_article_to_cluster(
    session: Session,
    cluster: Cluster,
    article: Article,
    score: float,
    heuristic_breakdown: dict,
) -> None:
    link = ClusterArticle(
        cluster_id=cluster.id,
        article_id=article.id,
        similarity_score=score,
        heuristic_breakdown=heuristic_breakdown,
    )
    session.add(link)
    session.flush()


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
        keywords=sorted(_semantic_keywords(article.keywords)),
        entities=sorted(_semantic_entities(article.entities)),
        topic=article.topic,
    )
    session.add(cluster)
    session.flush()
    return cluster


def cluster_new_articles(session: Session, settings: Settings) -> ClusteringRunResult:
    created_count = 0
    updated_count = 0
    candidates_evaluated = 0
    signal_rejected = 0
    attach_decisions = 0
    new_decisions = 0
    low_confidence_new = 0
    timeline_deduplicated = 0
    promoted_count = 0
    promotion_attempts = 0
    promotion_failures = 0
    invalid_cluster_ids: set[str] = set()

    pending = _load_unclustered_articles(session, settings.clustering_batch_size)

    for article in pending:
        article_features = _article_features(article)
        article.topic = article_features.topic
        candidates = _load_candidate_clusters(session, article, settings)

        best_evaluation: CandidateEvaluation | None = None
        strongest_evaluation: CandidateEvaluation | None = None

        for candidate_cluster in candidates:
            candidates_evaluated += 1
            cluster_features = _cluster_features(candidate_cluster)
            evaluation = _evaluate_candidate(candidate_cluster, article_features, cluster_features, settings)

            if _is_better_candidate(evaluation, strongest_evaluation, settings.cluster_tie_break_epsilon):
                strongest_evaluation = evaluation

            if not evaluation.signal_gate_passed:
                signal_rejected += 1
                continue

            if _is_better_candidate(evaluation, best_evaluation, settings.cluster_tie_break_epsilon):
                best_evaluation = evaluation

        decision_reason = ""
        chosen_score = 1.0

        if best_evaluation is None:
            cluster = _create_cluster(session, article)
            created_count += 1
            new_decisions += 1
            decision_reason = "no_candidate_clusters" if not candidates else "strongest_candidate_failed_semantic_gate"
            breakdown = _build_heuristic_breakdown(
                decision="create_new_cluster",
                decision_reason=decision_reason,
                candidate_count=len(candidates),
                settings=settings,
                evaluation=strongest_evaluation,
            )
        else:
            semantic_override_met = (
                best_evaluation.signal_gate_passed
                and best_evaluation.time_proximity >= settings.cluster_attach_override_min_time_proximity
                and any(
                    reason
                    in {
                        "meaningful_entity_overlap",
                        "meaningful_keyword_overlap",
                        "topic_semantic_similarity",
                        "topic_title_keyword_similarity",
                    }
                    for reason in best_evaluation.signal_reasons
                )
            )
            title_override_met = (
                best_evaluation.signal_gate_passed
                and best_evaluation.title_similarity >= settings.cluster_attach_override_min_title_similarity
                and best_evaluation.time_proximity >= settings.cluster_attach_override_min_time_proximity
                and "strong_title_similarity" in best_evaluation.signal_reasons
            )
            attach_override_met = semantic_override_met or title_override_met
            should_attach = best_evaluation.signal_gate_passed and (
                best_evaluation.score >= settings.cluster_score_threshold or attach_override_met
            )
            attach_override_components = {
                "signal_gate_passed": best_evaluation.signal_gate_passed,
                "signal_reasons": list(best_evaluation.signal_reasons),
                "topic_match": best_evaluation.topic_match,
                "keyword_overlap": best_evaluation.keyword_overlap,
                "keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
                "title_similarity": best_evaluation.title_similarity,
                "title_similarity_threshold": settings.cluster_attach_override_min_title_similarity,
                "semantic_score": best_evaluation.semantic_score,
                "topic_semantic_score_threshold": settings.cluster_min_topic_semantic_score,
                "time_proximity": best_evaluation.time_proximity,
                "time_proximity_threshold": settings.cluster_attach_override_min_time_proximity,
            }

            if should_attach:
                cluster = best_evaluation.cluster
                chosen_score = best_evaluation.score
                attach_decisions += 1
                decision_reason = (
                    "attached_to_existing_cluster_via_override"
                    if attach_override_met and best_evaluation.score < settings.cluster_score_threshold
                    else "attached_to_existing_cluster"
                )
                breakdown = _build_heuristic_breakdown(
                    decision="attach_existing_cluster",
                    decision_reason=decision_reason,
                    candidate_count=len(candidates),
                    settings=settings,
                    evaluation=best_evaluation,
                    attach_override_met=attach_override_met,
                    attach_override_components=attach_override_components,
                )
            else:
                cluster = _create_cluster(session, article)
                created_count += 1
                new_decisions += 1
                low_confidence_new += 1
                decision_reason = "best_candidate_below_score_threshold_and_no_safe_override"
                breakdown = _build_heuristic_breakdown(
                    decision="create_new_cluster",
                    decision_reason=decision_reason,
                    candidate_count=len(candidates),
                    settings=settings,
                    evaluation=best_evaluation,
                    attach_override_met=attach_override_met,
                    attach_override_components=attach_override_components,
                )

        _attach_article_to_cluster(session, cluster, article, chosen_score, breakdown)
        log_payload = {
            "article_id": article.id,
            "article_title": article.title,
            "decision": breakdown["decision"],
            "reason": decision_reason,
            "selected_cluster_id": cluster.id,
            "candidate_cluster_id": breakdown["selected_cluster_id"],
            "strongest_candidate_cluster_id": breakdown["selected_cluster_id"],
            "strongest_candidate_topic": breakdown["selected_topic"],
            "final_score": chosen_score,
            "candidate_score": breakdown["selected_score"],
            "title_similarity": breakdown["components"]["title_similarity"],
            "entity_jaccard": breakdown["components"]["entity_jaccard"],
            "keyword_jaccard": breakdown["components"]["keyword_jaccard"],
            "semantic_score": breakdown["components"]["semantic_score"],
            "entity_overlap": breakdown["overlap_counts"]["entity_overlap"],
            "keyword_overlap": breakdown["overlap_counts"]["keyword_overlap"],
            "location_overlap": breakdown["overlap_counts"]["location_overlap"],
            "source_match": breakdown["selected_source_match"],
            "topic_match": breakdown["selected_topic_match"],
            "time_proximity": breakdown["components"]["time_proximity"],
            "signal_gate_passed": breakdown["thresholds_met"]["signal_gate_passed"],
            "signal_reasons": breakdown["signal_reasons"],
            "warnings": breakdown["warnings"],
        }
        logger.info(
            "cluster_article_decision %s",
            json.dumps(log_payload, sort_keys=True, default=str),
        )
        rebuild_result = _rebuild_cluster(session, cluster, settings)
        if rebuild_result.validation_failed:
            invalid_cluster_ids.add(cluster.id)
        promotion_attempts += int(rebuild_result.promotion_attempted)
        promoted_count += int(rebuild_result.promoted)
        promotion_failures += int(rebuild_result.promotion_failed)

        updated_count += 1
        timeline_deduplicated += rebuild_result.timeline_deduplicated

    for cluster in _load_repromotable_hidden_clusters(session, settings):
        rebuild_result = _rebuild_cluster(session, cluster, settings)
        promotion_attempts += int(rebuild_result.promotion_attempted)
        promoted_count += int(rebuild_result.promoted)
        promotion_failures += int(rebuild_result.promotion_failed)
        if rebuild_result.validation_failed:
            invalid_cluster_ids.add(cluster.id)

    _refresh_related_clusters(session, settings)

    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    total_clusters = int(session.scalar(select(func.count()).select_from(Cluster)) or 0)
    active_total = int(
        session.scalar(
            select(func.count())
            .select_from(Cluster)
            .where(
                Cluster.status != "hidden",
                Cluster.validation_error.is_(None),
                source_count_subquery >= settings.cluster_min_sources_for_api,
            )
        )
        or 0
    )
    hidden_total = max(0, total_clusters - active_total)

    return ClusteringRunResult(
        created_count=created_count,
        updated_count=updated_count,
        candidates_evaluated=candidates_evaluated,
        signal_rejected=signal_rejected,
        attach_decisions=attach_decisions,
        new_decisions=new_decisions,
        low_confidence_new=low_confidence_new,
        validation_rejected=len(invalid_cluster_ids),
        timeline_deduplicated=timeline_deduplicated,
        promoted_count=promoted_count,
        hidden_total=hidden_total,
        active_total=active_total,
        promotion_attempts=promotion_attempts,
        promotion_failures=promotion_failures,
    )
