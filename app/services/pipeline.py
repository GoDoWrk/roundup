from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.clustering import cluster_new_articles
from app.services.ingestion import ingest_entries
from app.services.metrics import update_cluster_metrics, update_ingest_metrics
from app.services.miniflux_client import MinifluxClient, MinifluxClientError
from app.services.sample_data import load_sample_entries

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    ingestion_source: str
    fetched: int
    ingested: int
    deduplicated: int
    malformed: int
    clusters_created: int
    clusters_updated: int


def _load_entries_from_sample(path: Path) -> list[dict]:
    entries = load_sample_entries(path)
    logger.warning("sample_data_fallback_in_use path=%s entries=%s", path, len(entries))
    return entries


def _resolve_entries(settings: Settings) -> tuple[list[dict], str, bool]:
    sample_path = settings.sample_data_path

    if settings.demo_mode:
        if sample_path is not None:
            return _load_entries_from_sample(sample_path), "sample", False
        logger.error("demo_mode_enabled_but_sample_path_missing set SAMPLE_MINIFLUX_DATA_PATH")
        return [], "none", True

    if settings.has_miniflux_credentials:
        client = MinifluxClient(
            base_url=settings.miniflux_base_url,
            api_token=settings.miniflux_api_token_resolved,
            timeout_seconds=settings.miniflux_timeout_seconds,
        )
        try:
            entries = client.fetch_entries(limit=settings.miniflux_fetch_limit)
            if not entries:
                logger.info("pipeline_miniflux_returned_no_entries")
            return entries, "miniflux", False
        except MinifluxClientError as exc:
            logger.error("miniflux_fetch_failed error=%s", exc)
            logger.error("miniflux_ingestion_failed_no_sample_fallback demo_mode=%s", settings.demo_mode)
            return [], "miniflux_error", True

    logger.error(
        "no_ingestion_source_configured set MINIFLUX_URL + MINIFLUX_API_KEY(_FILE), or set DEMO_MODE=true with SAMPLE_MINIFLUX_DATA_PATH"
    )
    return [], "none", True


def run_pipeline(session: Session, settings: Settings, *, run_id: str = "manual") -> PipelineRunResult:
    started = time.monotonic()
    logger.info("pipeline_run_started run_id=%s", run_id)

    entries, ingestion_source, source_failure = _resolve_entries(settings)
    fetched = len(entries)

    ingest_result = ingest_entries(session, entries)
    update_ingest_metrics(
        session,
        ingest_result.ingested,
        ingest_result.deduplicated,
        malformed=ingest_result.malformed,
        source_failures=1 if source_failure else 0,
    )

    cluster_result = cluster_new_articles(session, settings)
    update_cluster_metrics(
        session,
        cluster_result.created_count,
        cluster_result.updated_count,
        candidates_evaluated=cluster_result.candidates_evaluated,
        signal_rejected=cluster_result.signal_rejected,
        attach_decisions=cluster_result.attach_decisions,
        new_decisions=cluster_result.new_decisions,
        low_confidence_new=cluster_result.low_confidence_new,
        validation_rejected=cluster_result.validation_rejected,
        timeline_deduplicated=cluster_result.timeline_deduplicated,
    )

    session.commit()

    result = PipelineRunResult(
        ingestion_source=ingestion_source,
        fetched=fetched,
        ingested=ingest_result.ingested,
        deduplicated=ingest_result.deduplicated,
        malformed=ingest_result.malformed,
        clusters_created=cluster_result.created_count,
        clusters_updated=cluster_result.updated_count,
    )

    duration = time.monotonic() - started
    logger.info(
        "pipeline_run_finished run_id=%s source=%s fetched=%s ingested=%s deduplicated=%s malformed=%s "
        "clusters_created=%s clusters_updated=%s source_failure=%s duration_seconds=%.2f",
        run_id,
        result.ingestion_source,
        result.fetched,
        result.ingested,
        result.deduplicated,
        result.malformed,
        result.clusters_created,
        result.clusters_updated,
        source_failure,
        duration,
    )

    if ingest_result.errors:
        logger.warning("pipeline_run_malformed_entries run_id=%s count=%s", run_id, len(ingest_result.errors))

    return result
