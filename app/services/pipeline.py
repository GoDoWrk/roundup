from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.clustering import cluster_new_articles
from app.services.content_quality import source_controls_from_payload
from app.services.ingestion import ingest_entries
from app.services.metrics import update_cluster_metrics, update_ingest_metrics
from app.services.miniflux_client import MinifluxClient, MinifluxClientError
from app.services.normalizer import parse_published_at
from app.services.sample_data import load_sample_entries

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    ingestion_source: str
    fetched: int
    ingested: int
    deduplicated: int
    malformed: int
    rejected: int
    source_failures: int
    clusters_created: int
    clusters_updated: int


@dataclass(frozen=True)
class IngestionFetchMetrics:
    configured_feed_count: int = 0
    active_feed_count: int = 0
    feeds_checked: int = 0
    feeds_with_new_articles: int = 0
    feed_failures: int = 0
    miniflux_entries_seen: int = 0
    articles_fetched_raw: int = 0


@dataclass(frozen=True)
class ResolvedEntries:
    entries: list[dict]
    source: str
    source_failure: bool
    metrics: IngestionFetchMetrics


def _load_entries_from_sample(path: Path) -> list[dict]:
    entries = load_sample_entries(path)
    logger.warning("sample_data_fallback_in_use path=%s entries=%s", path, len(entries))
    return entries


def _feed_id(feed: dict) -> int | None:
    try:
        return int(feed.get("id"))
    except (TypeError, ValueError):
        return None


def _feed_category(feed: dict) -> str:
    category = feed.get("category")
    if isinstance(category, dict):
        title = str(category.get("title") or "").strip()
        if title:
            return title
    return str(feed.get("category_title") or feed.get("category") or "Uncategorized").strip() or "Uncategorized"


def _entry_category(entry: dict) -> str:
    feed = entry.get("feed") if isinstance(entry.get("feed"), dict) else {}
    if isinstance(feed, dict):
        return _feed_category(feed)
    return "Uncategorized"


def _entry_published_at(entry: dict) -> datetime:
    value = str(entry.get("published_at") or entry.get("created_at") or "")
    try:
        return parse_published_at(value)
    except Exception:
        return datetime.now(timezone.utc)


def _with_feed_metadata(entry: dict, feed: dict) -> dict:
    copied = dict(entry)
    existing_feed = copied.get("feed") if isinstance(copied.get("feed"), dict) else {}
    merged_feed = dict(existing_feed)
    for key in ("id", "title", "feed_url", "site_url", "category"):
        if key in feed and key not in merged_feed:
            merged_feed[key] = feed[key]
    controls = source_controls_from_payload({"feed": merged_feed})
    merged_feed.setdefault("priority", controls.priority)
    merged_feed.setdefault("allow_service_content", controls.allow_service_content)
    merged_feed.setdefault("promote_to_home", controls.promote_to_home)
    copied["feed"] = merged_feed
    return copied


def _balanced_entries(entries: list[dict], *, max_total: int, quotas_enabled: bool) -> list[dict]:
    newest = sorted(entries, key=_entry_published_at, reverse=True)
    if not quotas_enabled:
        return newest[:max_total]

    grouped: dict[str, list[dict]] = {}
    for entry in newest:
        grouped.setdefault(_entry_category(entry), []).append(entry)

    categories = sorted(grouped)
    selected: list[dict] = []
    while categories and len(selected) < max_total:
        next_categories: list[str] = []
        for category in categories:
            bucket = grouped[category]
            if bucket and len(selected) < max_total:
                selected.append(bucket.pop(0))
            if bucket:
                next_categories.append(category)
        categories = next_categories
    return selected


def _fetch_miniflux_entries(client: MinifluxClient, settings: Settings) -> tuple[list[dict], IngestionFetchMetrics]:
    feeds = client.fetch_feeds()
    active_feeds = [feed for feed in feeds if not bool(feed.get("disabled"))]
    threshold = datetime.now(timezone.utc) - timedelta(hours=settings.ingest_lookback_hours)
    per_feed_cap = settings.ingest_max_articles_per_feed
    page_size = max(1, min(per_feed_cap, 100))

    candidates: list[dict] = []
    entries_seen = 0
    feeds_checked = 0
    feeds_with_new_articles = 0
    feed_failures = 0

    for feed in active_feeds:
        feed_id = _feed_id(feed)
        if feed_id is None:
            logger.warning(
                "miniflux_feed_skipped_invalid_id feed_title=%s feed_id=%s",
                feed.get("title"),
                feed.get("id"),
            )
            feed_failures += 1
            continue
        feeds_checked += 1
        accepted_for_feed = 0
        feed_had_recent = False

        for page in range(settings.ingest_max_pages):
            offset = page * page_size
            try:
                entries = client.fetch_feed_entries(feed_id, limit=page_size, offset=offset)
            except MinifluxClientError as exc:
                feed_failures += 1
                logger.warning(
                    "miniflux_feed_fetch_failed feed_id=%s feed_title=%s page=%s offset=%s error=%s",
                    feed_id,
                    feed.get("title"),
                    page + 1,
                    offset,
                    exc,
                )
                break
            entries_seen += len(entries)
            if not entries:
                logger.debug(
                    "miniflux_feed_empty feed_id=%s feed_title=%s offset=%s",
                    feed_id,
                    feed.get("title"),
                    offset,
                )
                break

            reached_old_entries = False
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                published_at = _entry_published_at(entry)
                if published_at < threshold:
                    reached_old_entries = True
                    continue
                feed_had_recent = True
                enriched = _with_feed_metadata(entry, feed)
                candidates.append(enriched)
                accepted_for_feed += 1
                if accepted_for_feed >= per_feed_cap:
                    break

            if accepted_for_feed >= per_feed_cap or reached_old_entries:
                break

        if feed_had_recent:
            feeds_with_new_articles += 1

    selected = _balanced_entries(
        candidates,
        max_total=settings.ingest_max_total_articles,
        quotas_enabled=settings.ingest_category_quotas_enabled,
    )
    logger.info(
        "miniflux_feed_fetch_summary configured_feed_count=%s active_feed_count=%s feeds_checked=%s "
        "feeds_with_new_articles=%s feed_failures=%s entries_seen=%s candidates=%s selected=%s",
        len(feeds),
        len(active_feeds),
        feeds_checked,
        feeds_with_new_articles,
        feed_failures,
        entries_seen,
        len(candidates),
        len(selected),
    )
    return selected, IngestionFetchMetrics(
        configured_feed_count=len(feeds),
        active_feed_count=len(active_feeds),
        feeds_checked=feeds_checked,
        feeds_with_new_articles=feeds_with_new_articles,
        feed_failures=feed_failures,
        miniflux_entries_seen=entries_seen,
        articles_fetched_raw=len(candidates),
    )


def _resolve_entries(settings: Settings) -> ResolvedEntries:
    sample_path = settings.sample_data_path

    if settings.demo_mode:
        if sample_path is not None:
            entries = _load_entries_from_sample(sample_path)
            return ResolvedEntries(
                entries,
                "sample",
                False,
                IngestionFetchMetrics(
                    configured_feed_count=1,
                    active_feed_count=1,
                    feeds_checked=1,
                    feeds_with_new_articles=1 if entries else 0,
                    miniflux_entries_seen=len(entries),
                    articles_fetched_raw=len(entries),
                ),
            )
        logger.error("demo_mode_enabled_but_sample_path_missing set SAMPLE_MINIFLUX_DATA_PATH")
        return ResolvedEntries([], "none", True, IngestionFetchMetrics())

    if settings.has_miniflux_credentials:
        client = MinifluxClient(
            base_url=settings.miniflux_base_url,
            api_token=settings.miniflux_api_token_resolved,
            timeout_seconds=settings.miniflux_timeout_seconds,
            request_retries=settings.miniflux_request_retries,
        )
        try:
            entries, fetch_metrics = _fetch_miniflux_entries(client, settings)
            if not entries:
                logger.info("pipeline_miniflux_returned_no_entries")
            return ResolvedEntries(entries, "miniflux", False, fetch_metrics)
        except MinifluxClientError as exc:
            logger.error("miniflux_fetch_failed error=%s", exc)
            logger.error("miniflux_ingestion_failed_no_sample_fallback demo_mode=%s", settings.demo_mode)
            return ResolvedEntries([], "miniflux_error", True, IngestionFetchMetrics())

    logger.error(
        "no_ingestion_source_configured set MINIFLUX_URL + MINIFLUX_API_KEY(_FILE), or set DEMO_MODE=true with SAMPLE_MINIFLUX_DATA_PATH"
    )
    return ResolvedEntries([], "none", True, IngestionFetchMetrics())


def run_pipeline(session: Session, settings: Settings, *, run_id: str = "manual") -> PipelineRunResult:
    started = time.monotonic()
    logger.info("pipeline_run_started run_id=%s", run_id)

    resolved = _resolve_entries(settings)
    entries = resolved.entries
    ingestion_source = resolved.source
    source_failure = resolved.source_failure
    source_failures = resolved.metrics.feed_failures + (1 if source_failure else 0)
    fetched = len(entries)

    ingest_result = ingest_entries(session, entries)
    update_ingest_metrics(
        session,
        ingest_result.ingested,
        ingest_result.deduplicated,
        fetched=fetched,
        malformed=ingest_result.malformed,
        rejected=ingest_result.rejected,
        rejected_stale=ingest_result.rejected_stale,
        rejected_service_finance=ingest_result.rejected_service_finance,
        source_failures=source_failures,
        configured_feed_count=resolved.metrics.configured_feed_count,
        active_feed_count=resolved.metrics.active_feed_count,
        feeds_checked=resolved.metrics.feeds_checked,
        feeds_with_new_articles=resolved.metrics.feeds_with_new_articles,
        miniflux_entries_seen=resolved.metrics.miniflux_entries_seen,
        articles_fetched_raw=resolved.metrics.articles_fetched_raw,
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
        promoted=cluster_result.promoted_count,
        hidden_total=cluster_result.hidden_total,
        active_total=cluster_result.active_total,
        promotion_attempts=cluster_result.promotion_attempts,
        promotion_failures=cluster_result.promotion_failures,
    )

    session.commit()

    result = PipelineRunResult(
        ingestion_source=ingestion_source,
        fetched=fetched,
        ingested=ingest_result.ingested,
        deduplicated=ingest_result.deduplicated,
        malformed=ingest_result.malformed,
        rejected=ingest_result.rejected,
        source_failures=source_failures,
        clusters_created=cluster_result.created_count,
        clusters_updated=cluster_result.updated_count,
    )

    duration = time.monotonic() - started
    logger.info(
        "pipeline_run_finished run_id=%s source=%s fetched=%s ingested=%s deduplicated=%s malformed=%s rejected=%s "
        "clusters_created=%s clusters_updated=%s source_failure=%s source_failures=%s duration_seconds=%.2f",
        run_id,
        result.ingestion_source,
        result.fetched,
        result.ingested,
        result.deduplicated,
        result.malformed,
        result.rejected,
        result.clusters_created,
        result.clusters_updated,
        source_failure,
        source_failures,
        duration,
    )

    if ingest_result.errors:
        logger.warning("pipeline_run_malformed_entries run_id=%s count=%s", run_id, len(ingest_result.errors))

    return result
