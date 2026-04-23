from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import PipelineStats


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
    malformed: int = 0,
    source_failures: int = 0,
) -> None:
    stats = get_or_create_pipeline_stats(session)
    stats.articles_ingested_total += ingested
    stats.articles_deduplicated_total += deduplicated
    stats.articles_malformed_total += malformed
    stats.ingest_source_failures_total += source_failures
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
    stats.last_cluster_time = utcnow()


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
        "# HELP last_ingest_time Unix timestamp for the last ingest run",
        "# TYPE last_ingest_time gauge",
        f"last_ingest_time {ingest_ts}",
        "# HELP last_cluster_time Unix timestamp for the last clustering run",
        "# TYPE last_cluster_time gauge",
        f"last_cluster_time {cluster_ts}",
    ]
    return "\n".join(lines) + "\n"
