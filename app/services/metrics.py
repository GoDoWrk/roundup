from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle, PipelineStats


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_pipeline_stats(session: Session) -> PipelineStats:
    stats = session.get(PipelineStats, 1)
    if stats is None:
        stats = PipelineStats(id=1)
        session.add(stats)
        session.flush()
    return stats


def update_ingest_metrics(
    session: Session,
    ingested: int,
    deduplicated: int,
    *,
    fetched: int = 0,
    malformed: int = 0,
    source_failures: int = 0,
) -> None:
    stats = get_or_create_pipeline_stats(session)
    stats.articles_ingested_total += ingested
    stats.articles_deduplicated_total += deduplicated
    stats.articles_malformed_total += malformed
    stats.ingest_source_failures_total += source_failures
    stats.latest_articles_fetched = fetched
    stats.latest_articles_stored = ingested
    stats.latest_duplicate_articles_skipped = deduplicated
    stats.latest_articles_malformed = malformed
    stats.latest_failed_source_count = source_failures
    stats.last_ingest_time = utcnow()


def update_cluster_metrics(
    session: Session,
    created: int,
    updated: int,
    *,
    candidates_evaluated: int = 0,
    signal_rejected: int = 0,
    attach_decisions: int = 0,
    new_decisions: int = 0,
    low_confidence_new: int = 0,
    validation_rejected: int = 0,
    timeline_deduplicated: int = 0,
    promoted: int = 0,
    hidden_total: int = 0,
    active_total: int = 0,
    promotion_attempts: int = 0,
    promotion_failures: int = 0,
) -> None:
    stats = get_or_create_pipeline_stats(session)
    stats.clusters_created_total += created
    stats.clusters_updated_total += updated
    stats.cluster_candidates_evaluated_total += candidates_evaluated
    stats.cluster_signal_rejected_total += signal_rejected
    stats.cluster_attach_decisions_total += attach_decisions
    stats.cluster_new_decisions_total += new_decisions
    stats.cluster_low_confidence_new_total += low_confidence_new
    stats.cluster_validation_rejected_total += validation_rejected
    stats.cluster_timeline_events_deduplicated_total += timeline_deduplicated
    stats.clusters_promoted_total += promoted
    stats.clusters_hidden_total = hidden_total
    stats.clusters_active_total = active_total
    stats.cluster_promotion_attempts_total += promotion_attempts
    stats.cluster_promotion_failures_total += promotion_failures
    stats.latest_candidate_clusters_created = created
    stats.latest_clusters_updated = updated
    stats.latest_clusters_hidden = hidden_total
    stats.latest_clusters_promoted = promoted
    stats.latest_visible_clusters = active_total
    stats.last_cluster_time = utcnow()


def count_articles_pending_clustering(session: Session) -> int:
    stmt: Select[tuple[int]] = (
        select(func.count())
        .select_from(Article)
        .outerjoin(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.id.is_(None))
    )
    return int(session.scalar(stmt) or 0)


def count_summaries_pending(session: Session) -> int:
    placeholder = "%pending%"
    stmt = (
        select(func.count())
        .select_from(Cluster)
        .where(
            (Cluster.headline.ilike(placeholder))
            | (Cluster.summary.ilike(placeholder))
            | (Cluster.what_changed.ilike(placeholder))
            | (Cluster.why_it_matters.ilike(placeholder))
        )
    )
    return int(session.scalar(stmt) or 0)


def count_active_sources(session: Session) -> int:
    stmt = select(func.count(func.distinct(Article.publisher))).where(Article.publisher != "unknown")
    return int(session.scalar(stmt) or 0)


def metrics_as_prometheus_text(session: Session) -> str:
    stats = get_or_create_pipeline_stats(session)
    ingest_ts = int(stats.last_ingest_time.timestamp()) if stats.last_ingest_time else 0
    cluster_ts = int(stats.last_cluster_time.timestamp()) if stats.last_cluster_time else 0

    lines = [
        "# HELP articles_ingested_total Total number of ingested articles",
        "# TYPE articles_ingested_total counter",
        f"articles_ingested_total {stats.articles_ingested_total}",
        "# HELP articles_deduplicated_total Total number of deduplicated articles",
        "# TYPE articles_deduplicated_total counter",
        f"articles_deduplicated_total {stats.articles_deduplicated_total}",
        "# HELP articles_malformed_total Total number of malformed articles skipped during ingestion",
        "# TYPE articles_malformed_total counter",
        f"articles_malformed_total {stats.articles_malformed_total}",
        "# HELP ingest_source_failures_total Total number of ingestion source fetch failures",
        "# TYPE ingest_source_failures_total counter",
        f"ingest_source_failures_total {stats.ingest_source_failures_total}",
        "# HELP latest_articles_fetched Articles fetched in the latest pipeline run",
        "# TYPE latest_articles_fetched gauge",
        f"latest_articles_fetched {stats.latest_articles_fetched}",
        "# HELP latest_articles_stored Articles stored in the latest pipeline run",
        "# TYPE latest_articles_stored gauge",
        f"latest_articles_stored {stats.latest_articles_stored}",
        "# HELP latest_duplicate_articles_skipped Duplicate articles skipped in the latest pipeline run",
        "# TYPE latest_duplicate_articles_skipped gauge",
        f"latest_duplicate_articles_skipped {stats.latest_duplicate_articles_skipped}",
        "# HELP latest_articles_malformed Malformed articles skipped in the latest pipeline run",
        "# TYPE latest_articles_malformed gauge",
        f"latest_articles_malformed {stats.latest_articles_malformed}",
        "# HELP latest_failed_source_count Source failures in the latest pipeline run",
        "# TYPE latest_failed_source_count gauge",
        f"latest_failed_source_count {stats.latest_failed_source_count}",
        "# HELP clusters_created_total Total number of created clusters",
        "# TYPE clusters_created_total counter",
        f"clusters_created_total {stats.clusters_created_total}",
        "# HELP clusters_updated_total Total number of updated clusters",
        "# TYPE clusters_updated_total counter",
        f"clusters_updated_total {stats.clusters_updated_total}",
        "# HELP cluster_candidates_evaluated_total Total candidate cluster comparisons evaluated",
        "# TYPE cluster_candidates_evaluated_total counter",
        f"cluster_candidates_evaluated_total {stats.cluster_candidates_evaluated_total}",
        "# HELP cluster_signal_rejected_total Total candidate clusters rejected by minimum signal gate",
        "# TYPE cluster_signal_rejected_total counter",
        f"cluster_signal_rejected_total {stats.cluster_signal_rejected_total}",
        "# HELP cluster_attach_decisions_total Total decisions to attach an article to an existing cluster",
        "# TYPE cluster_attach_decisions_total counter",
        f"cluster_attach_decisions_total {stats.cluster_attach_decisions_total}",
        "# HELP cluster_new_decisions_total Total decisions to create a new cluster",
        "# TYPE cluster_new_decisions_total counter",
        f"cluster_new_decisions_total {stats.cluster_new_decisions_total}",
        "# HELP cluster_low_confidence_new_total Total new clusters created because candidate score was below threshold",
        "# TYPE cluster_low_confidence_new_total counter",
        f"cluster_low_confidence_new_total {stats.cluster_low_confidence_new_total}",
        "# HELP cluster_validation_rejected_total Total cluster rebuilds rejected by validation",
        "# TYPE cluster_validation_rejected_total counter",
        f"cluster_validation_rejected_total {stats.cluster_validation_rejected_total}",
        "# HELP cluster_timeline_events_deduplicated_total Total timeline events removed by near-duplicate collapse",
        "# TYPE cluster_timeline_events_deduplicated_total counter",
        f"cluster_timeline_events_deduplicated_total {stats.cluster_timeline_events_deduplicated_total}",
        "# HELP clusters_promoted_total Total number of hidden clusters promoted to API-eligible visibility",
        "# TYPE clusters_promoted_total counter",
        f"clusters_promoted_total {stats.clusters_promoted_total}",
        "# HELP clusters_hidden_total Current number of debug-only hidden clusters",
        "# TYPE clusters_hidden_total gauge",
        f"clusters_hidden_total {stats.clusters_hidden_total}",
        "# HELP clusters_active_total Current number of API-visible active clusters",
        "# TYPE clusters_active_total gauge",
        f"clusters_active_total {stats.clusters_active_total}",
        "# HELP cluster_promotion_attempts_total Total hidden-cluster rebuild attempts that could trigger promotion",
        "# TYPE cluster_promotion_attempts_total counter",
        f"cluster_promotion_attempts_total {stats.cluster_promotion_attempts_total}",
        "# HELP cluster_promotion_failures_total Total hidden-cluster promotion attempts that remained hidden",
        "# TYPE cluster_promotion_failures_total counter",
        f"cluster_promotion_failures_total {stats.cluster_promotion_failures_total}",
        "# HELP latest_candidate_clusters_created Candidate clusters created in the latest pipeline run",
        "# TYPE latest_candidate_clusters_created gauge",
        f"latest_candidate_clusters_created {stats.latest_candidate_clusters_created}",
        "# HELP latest_clusters_updated Clusters updated in the latest pipeline run",
        "# TYPE latest_clusters_updated gauge",
        f"latest_clusters_updated {stats.latest_clusters_updated}",
        "# HELP latest_clusters_hidden Current hidden cluster count captured by the latest clustering run",
        "# TYPE latest_clusters_hidden gauge",
        f"latest_clusters_hidden {stats.latest_clusters_hidden}",
        "# HELP latest_clusters_promoted Clusters promoted in the latest pipeline run",
        "# TYPE latest_clusters_promoted gauge",
        f"latest_clusters_promoted {stats.latest_clusters_promoted}",
        "# HELP latest_visible_clusters Current visible cluster count captured by the latest clustering run",
        "# TYPE latest_visible_clusters gauge",
        f"latest_visible_clusters {stats.latest_visible_clusters}",
        "# HELP articles_pending_clustering Current articles not attached to any cluster",
        "# TYPE articles_pending_clustering gauge",
        f"articles_pending_clustering {count_articles_pending_clustering(session)}",
        "# HELP summaries_pending Current clusters with placeholder summary fields",
        "# TYPE summaries_pending gauge",
        f"summaries_pending {count_summaries_pending(session)}",
        "# HELP active_sources Current distinct publishers stored by Roundup",
        "# TYPE active_sources gauge",
        f"active_sources {count_active_sources(session)}",
        "# HELP last_ingest_time Unix timestamp for the last ingest run",
        "# TYPE last_ingest_time gauge",
        f"last_ingest_time {ingest_ts}",
        "# HELP last_cluster_time Unix timestamp for the last clustering run",
        "# TYPE last_cluster_time gauge",
        f"last_cluster_time {cluster_ts}",
    ]
    return "\n".join(lines) + "\n"
