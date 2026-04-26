from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Article, Cluster, ClusterArticle
from app.db.session import get_db_session
from app.schemas.article import ArticleDebugResponse
from app.schemas.cluster import (
    ClusterDebugExplanation,
    ClusterDebugItem,
    ClusterDebugJoinDecision,
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


def _location_diversity_warning(cluster: Cluster) -> str | None:
    location_terms = {
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
    seen: set[str] = set()
    for link in cluster.source_links:
        article = link.article
        if article is None:
            continue
        terms = {str(term).strip().lower() for term in (article.entities + article.keywords) if str(term).strip()}
        title_terms = {part.strip().lower() for part in (article.title or "").replace("-", " ").split() if part.strip()}
        seen.update(terms.intersection(location_terms))
        seen.update(title_terms.intersection(location_terms))
    if len(seen) >= 3:
        return "cluster_location_diversity_warning"
    return None


def _build_debug_explanation(cluster: Cluster) -> ClusterDebugExplanation:
    settings = get_settings()
    links = list(cluster.source_links)
    decision_counts: Counter[str] = Counter()

    components = {
        "title_similarity": [],
        "entity_jaccard": [],
        "keyword_jaccard": [],
        "semantic_score": [],
        "time_proximity": [],
        "score": [],
    }
    recent_join_decisions: list[ClusterDebugJoinDecision] = []
    warning_counts: Counter[str] = Counter()

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
        for key in ("title_similarity", "entity_jaccard", "keyword_jaccard", "semantic_score", "time_proximity"):
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

        warnings = [str(item) for item in breakdown.get("warnings") or [] if str(item)]
        warning_counts.update(warnings)
        article = link.article
        recent_join_decisions.append(
            ClusterDebugJoinDecision(
                article_id=article.id if article is not None else link.article_id,
                article_title=article.title if article is not None else "",
                publisher=article.publisher if article is not None else "",
                decision=str(breakdown.get("decision") or "unknown"),
                reason=str(breakdown.get("decision_reason") or ""),
                selected_cluster_id=breakdown.get("selected_cluster_id"),
                selected_score=round(float(breakdown.get("selected_score") or 0.0), 4),
                title_similarity=round(float(component_values.get("title_similarity") or 0.0), 4),
                entity_jaccard=round(float(component_values.get("entity_jaccard") or 0.0), 4),
                keyword_jaccard=round(float(component_values.get("keyword_jaccard") or 0.0), 4),
                semantic_score=round(float(component_values.get("semantic_score") or 0.0), 4),
                entity_overlap=int((breakdown.get("overlap_counts") or {}).get("entity_overlap") or 0),
                keyword_overlap=int((breakdown.get("overlap_counts") or {}).get("keyword_overlap") or 0),
                location_overlap=int((breakdown.get("overlap_counts") or {}).get("location_overlap") or 0),
                source_match=bool(breakdown.get("selected_source_match")),
                topic_match=bool(breakdown.get("selected_topic_match")),
                time_proximity=round(float(component_values.get("time_proximity") or 0.0), 4),
                signal_gate_passed=bool(met.get("signal_gate_passed")),
                signal_reasons=[str(item) for item in breakdown.get("signal_reasons") or [] if str(item)],
                warnings=warnings,
            )
        )

    def average(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    shared_entities = _top_shared_terms(cluster, attr="entities")
    shared_keywords = _top_shared_terms(cluster, attr="keywords")
    topic_text = ", ".join((shared_entities + shared_keywords)[:3]) or "shared reporting themes"
    cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))

    score_formula = "0.45*title_similarity + 0.25*entity_jaccard + 0.20*keyword_jaccard + 0.10*time_proximity"
    semantic_formula = "0.50*title_similarity + 0.30*entity_jaccard + 0.20*keyword_jaccard"
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
    quality_warning = _location_diversity_warning(cluster)
    if quality_warning:
        warning_counts.update([quality_warning])

    return ClusterDebugExplanation(
        grouping_reason=grouping_reason,
        thresholds=ClusterDebugThresholds(
            score_threshold=settings.cluster_score_threshold,
            title_signal_threshold=settings.cluster_min_title_signal,
            entity_overlap_threshold=settings.cluster_min_entity_overlap,
            keyword_overlap_threshold=settings.cluster_min_keyword_overlap,
            topic_semantic_score_threshold=settings.cluster_min_topic_semantic_score,
            attach_override_title_similarity_threshold=settings.cluster_attach_override_min_title_similarity,
            attach_override_time_proximity_threshold=settings.cluster_attach_override_min_time_proximity,
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
            average_semantic_score=average(components["semantic_score"]),
            average_time_proximity=average(components["time_proximity"]),
            score_formula=score_formula,
            semantic_formula=semantic_formula,
        ),
        decision_counts={key: int(value) for key, value in sorted(decision_counts.items())},
        recent_join_decisions=sorted(
            recent_join_decisions,
            key=lambda item: item.article_id,
            reverse=True,
        )[:8],
        warnings=[key for key, _ in warning_counts.most_common()],
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
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .options(
            selectinload(Cluster.source_links).selectinload(ClusterArticle.article),
            selectinload(Cluster.timeline_events),
        )
        .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
    )
    rows = list(db.scalars(stmt).unique().all())

    items: list[ClusterDebugItem] = []
    for cluster in rows:
        source_count = len(cluster.source_links)
        cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))
        visibility_threshold = settings.cluster_min_sources_for_api
        promotion_blockers = _promotion_blockers(
            source_count=source_count,
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
