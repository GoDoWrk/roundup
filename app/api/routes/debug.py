from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Article, Cluster
from app.db.session import get_db_session
from app.schemas.article import ArticleDebugResponse
from app.schemas.cluster import (
    ClusterDebugExplanation,
    ClusterDebugItem,
    ClusterDebugResponse,
    ClusterDebugScoreBreakdown,
    ClusterDebugThresholds,
)
from app.services.serialization import article_to_debug
from app.services.clustering import _promotion_blockers
from app.services.topics import derive_topic_from_articles

router = APIRouter(prefix="/debug", tags=["debug"])


def _top_shared_terms(cluster: Cluster, *, attr: str, limit: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    for link in cluster.source_links:
        article = link.article
        if article is None:
            continue
        terms = {str(term).strip() for term in getattr(article, attr, []) if str(term).strip()}
        counter.update(terms)

    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    shared = [term for term, count in ranked if count >= 2]
    return (shared or [term for term, _ in ranked])[:limit]


def _build_debug_explanation(cluster: Cluster) -> ClusterDebugExplanation:
    settings = get_settings()
    links = list(cluster.source_links)
    decision_counts: Counter[str] = Counter()

    components = {
        "title_similarity": [],
        "entity_jaccard": [],
        "keyword_jaccard": [],
        "time_proximity": [],
        "score": [],
    }

    threshold_results = {
        "score_threshold_met": cluster.score >= settings.cluster_score_threshold,
        "source_count_threshold_met": len(links) >= settings.cluster_min_sources_for_api,
        "signal_gate_seen": False,
        "title_signal_seen": False,
        "entity_overlap_seen": False,
        "keyword_overlap_seen": False,
        "attach_override_seen": False,
    }

    for link in links:
        breakdown = link.heuristic_breakdown or {}
        decision_counts.update([str(breakdown.get("decision") or "unknown")])

        component_values = breakdown.get("components") or {}
        for key in ("title_similarity", "entity_jaccard", "keyword_jaccard", "time_proximity"):
            value = component_values.get(key)
            if isinstance(value, (int, float)):
                components[key].append(float(value))

        selected_score = breakdown.get("selected_score")
        if isinstance(selected_score, (int, float)):
            components["score"].append(float(selected_score))

        met = breakdown.get("thresholds_met") or {}
        if met.get("signal_gate_passed"):
            threshold_results["signal_gate_seen"] = True
        if met.get("title_signal_met"):
            threshold_results["title_signal_seen"] = True
        if met.get("entity_overlap_met"):
            threshold_results["entity_overlap_seen"] = True
        if met.get("keyword_overlap_met"):
            threshold_results["keyword_overlap_seen"] = True
        if met.get("attach_override_met"):
            threshold_results["attach_override_seen"] = True

    def average(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    shared_entities = _top_shared_terms(cluster, attr="entities")
    shared_keywords = _top_shared_terms(cluster, attr="keywords")
    topic_text = ", ".join((shared_entities + shared_keywords)[:3]) or "shared reporting themes"
    cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))

    score_formula = "0.45*title_similarity + 0.25*entity_jaccard + 0.20*keyword_jaccard + 0.10*time_proximity"
    score_summary = (
        "Score is a weighted blend of title similarity, shared entities, shared keywords, and recency. "
        "Higher scores usually mean a tighter match; lower scores usually mean broader or more mixed coverage."
    )

    attach_count = decision_counts.get("attach_existing_cluster", 0)
    create_count = decision_counts.get("create_new_cluster", 0)
    grouping_reason = (
        f"{attach_count} article attachments and {create_count} new-cluster decisions were made within the topic "
        f"'{cluster_topic}' using a weighted score ({score_formula}). {score_summary} "
        f"The main shared themes were {topic_text}."
    )

    return ClusterDebugExplanation(
        grouping_reason=grouping_reason,
        thresholds=ClusterDebugThresholds(
            score_threshold=settings.cluster_score_threshold,
            title_signal_threshold=settings.cluster_min_title_signal,
            entity_overlap_threshold=settings.cluster_min_entity_overlap,
            keyword_overlap_threshold=settings.cluster_min_keyword_overlap,
            min_sources_for_api=settings.cluster_min_sources_for_api,
        ),
        threshold_results=threshold_results,
        top_shared_entities=shared_entities,
        top_shared_keywords=shared_keywords,
        score_breakdown=ClusterDebugScoreBreakdown(
            average_similarity_score=average(components["score"]),
            average_title_similarity=average(components["title_similarity"]),
            average_entity_jaccard=average(components["entity_jaccard"]),
            average_keyword_jaccard=average(components["keyword_jaccard"]),
            average_time_proximity=average(components["time_proximity"]),
            score_formula=score_formula,
        ),
        decision_counts={key: int(value) for key, value in sorted(decision_counts.items())},
    )


@router.get("/articles", response_model=ArticleDebugResponse)
def debug_articles(db: Session = Depends(get_db_session)) -> ArticleDebugResponse:
    total = int(db.scalar(select(func.count()).select_from(Article)) or 0)
    stmt: Select[tuple[Article]] = select(Article).order_by(Article.published_at.desc(), Article.id.desc())
    rows = list(db.scalars(stmt).all())
    return ArticleDebugResponse(total=total, items=[article_to_debug(article) for article in rows])


@router.get("/clusters", response_model=ClusterDebugResponse)
def debug_clusters(db: Session = Depends(get_db_session)) -> ClusterDebugResponse:
    settings = get_settings()
    stmt: Select[tuple[Cluster]] = select(Cluster).order_by(Cluster.last_updated.desc(), Cluster.id.asc())
    rows = list(db.scalars(stmt).all())

    items: list[ClusterDebugItem] = []
    for cluster in rows:
        source_count = len(cluster.source_links)
        cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))
        visibility_threshold = settings.cluster_min_sources_for_api
        promotion_blockers = _promotion_blockers(
            source_count=source_count,
            score=cluster.score,
            validation_error=cluster.validation_error,
            settings=settings,
        )
        promotion_eligible = not promotion_blockers
        items.append(
            ClusterDebugItem(
                cluster_id=cluster.id,
                status=cluster.status,
                score=cluster.score,
                topic=cluster_topic,
                source_count=source_count,
                visibility_threshold=visibility_threshold,
                promotion_eligible=promotion_eligible,
                promoted_at=cluster.promoted_at,
                previous_status=cluster.previous_status,
                promotion_reason=cluster.promotion_reason,
                promotion_explanation=cluster.promotion_explanation,
                promotion_blockers=promotion_blockers,
                validation_error=cluster.validation_error,
                headline=cluster.headline,
                summary=cluster.summary,
                debug_explanation=_build_debug_explanation(cluster),
            )
        )

    return ClusterDebugResponse(total=len(items), items=items)
