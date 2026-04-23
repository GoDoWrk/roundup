from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.clustering import cluster_new_articles
from app.services.ingestion import ingest_entries
from app.services.metrics import update_cluster_metrics, update_ingest_metrics
from app.services.miniflux_client import MinifluxClient

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    fetched: int
    ingested: int
    deduplicated: int
    clusters_created: int
    clusters_updated: int


def run_pipeline(session: Session, settings: Settings) -> PipelineRunResult:
    client = MinifluxClient(base_url=settings.miniflux_base_url, api_token=settings.miniflux_api_token)
    entries = client.fetch_entries(limit=settings.miniflux_fetch_limit)
    fetched = len(entries)

    ingest_result = ingest_entries(session, entries)
    update_ingest_metrics(session, ingest_result.ingested, ingest_result.deduplicated)

    clusters_created, clusters_updated = cluster_new_articles(session, settings)
    update_cluster_metrics(session, clusters_created, clusters_updated)

    session.commit()

    result = PipelineRunResult(
        fetched=fetched,
        ingested=ingest_result.ingested,
        deduplicated=ingest_result.deduplicated,
        clusters_created=clusters_created,
        clusters_updated=clusters_updated,
    )

    logger.info(
        "pipeline_run fetched=%s ingested=%s deduplicated=%s clusters_created=%s clusters_updated=%s",
        result.fetched,
        result.ingested,
        result.deduplicated,
        result.clusters_created,
        result.clusters_updated,
    )
    return result
