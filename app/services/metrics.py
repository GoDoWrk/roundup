from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
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


def update_ingest_metrics(session: Session, ingested: int, deduplicated: int) -> None:
    stats = get_or_create_pipeline_stats(session)
    stats.articles_ingested_total += ingested
    stats.articles_deduplicated_total += deduplicated
    stats.last_ingest_time = utcnow()


def update_cluster_metrics(session: Session, created: int, updated: int) -> None:
    stats = get_or_create_pipeline_stats(session)
    stats.clusters_created_total += created
    stats.clusters_updated_total += updated
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
        "# HELP clusters_created_total Total number of created clusters",
        "# TYPE clusters_created_total counter",
        f"clusters_created_total {stats.clusters_created_total}",
        "# HELP clusters_updated_total Total number of updated clusters",
        "# TYPE clusters_updated_total counter",
        f"clusters_updated_total {stats.clusters_updated_total}",
        "# HELP last_ingest_time Unix timestamp for the last ingest run",
        "# TYPE last_ingest_time gauge",
        f"last_ingest_time {ingest_ts}",
        "# HELP last_cluster_time Unix timestamp for the last clustering run",
        "# TYPE last_cluster_time gauge",
        f"last_cluster_time {cluster_ts}",
    ]
    return "\n".join(lines) + "\n"
