from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.core.config import Settings
from app.core.url_security import safe_feed_url
from app.db.models import Article
from app.schemas.source import SourceHealthItem, SourceListResponse
from app.services.miniflux_client import MinifluxClient, MinifluxClientError

logger = logging.getLogger(__name__)

RECENT_ARTICLE_WINDOW_DAYS = 7


@dataclass
class SourceArticleStats:
    count: int = 0
    last_fetched_at: datetime | None = None
    display_name: str = ""

    def add(self, fetched_at: datetime, display_name: str = "") -> None:
        self.count += 1
        if display_name and not self.display_name:
            self.display_name = display_name
        if self.last_fetched_at is None or fetched_at > self.last_fetched_at:
            self.last_fetched_at = fetched_at


def _normalize_lookup_key(value: object) -> str:
    return str(value or "").strip().casefold()


def _safe_public_feed_url(value: object) -> str | None:
    return safe_feed_url(value, allow_private_network=False)


def _feed_id_from_raw_payload(raw_payload: dict) -> str:
    feed = raw_payload.get("feed") if isinstance(raw_payload, dict) else None
    if not isinstance(feed, dict):
        return ""
    return str(feed.get("id") or feed.get("feed_id") or "").strip()


def _feed_title_from_raw_payload(raw_payload: dict) -> str:
    feed = raw_payload.get("feed") if isinstance(raw_payload, dict) else None
    if not isinstance(feed, dict):
        return ""
    return str(feed.get("title") or "").strip()


def _recent_article_stats(session: Session) -> tuple[dict[str, SourceArticleStats], dict[str, SourceArticleStats]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_ARTICLE_WINDOW_DAYS)
    rows = list(
        session.scalars(
            select(Article)
            .options(load_only(Article.fetched_at, Article.raw_payload, Article.publisher))
            .where(Article.fetched_at >= cutoff)
            .order_by(Article.fetched_at.desc(), Article.id.desc())
        ).all()
    )
    by_feed_id: dict[str, SourceArticleStats] = defaultdict(SourceArticleStats)
    by_name: dict[str, SourceArticleStats] = defaultdict(SourceArticleStats)

    for article in rows:
        feed_id = _feed_id_from_raw_payload(article.raw_payload or {})
        feed_title = _feed_title_from_raw_payload(article.raw_payload or {})
        name_keys: set[tuple[str, str]] = set()

        if feed_id:
            by_feed_id[feed_id].add(article.fetched_at, feed_title or article.publisher)
        if feed_title:
            name_keys.add((_normalize_lookup_key(feed_title), feed_title))
        elif article.publisher:
            name_keys.add((_normalize_lookup_key(article.publisher), article.publisher))
        for key, display_name in name_keys:
            by_name[key].add(article.fetched_at, display_name)

    return dict(by_feed_id), dict(by_name)


def _stats_for_feed(
    feed: dict,
    by_feed_id: dict[str, SourceArticleStats],
    by_name: dict[str, SourceArticleStats],
) -> SourceArticleStats:
    feed_id = str(feed.get("id") or "").strip()
    title = _normalize_lookup_key(feed.get("title"))

    if feed_id and feed_id in by_feed_id:
        return by_feed_id[feed_id]
    if title and title in by_name:
        return by_name[title]
    return SourceArticleStats()


def _category_title(feed: dict) -> str | None:
    category = feed.get("category")
    if not isinstance(category, dict):
        return None
    title = str(category.get("title") or "").strip()
    return title or None


def _error_status(feed: dict) -> tuple[str, str | None]:
    message = str(feed.get("parsing_error_message") or "").strip()
    try:
        error_count = int(feed.get("parsing_error_count") or 0)
    except (TypeError, ValueError):
        error_count = 0

    if message or error_count > 0:
        return "error", message or f"{error_count} recent parsing errors"
    return "ok", None


def _item_from_miniflux_feed(
    feed: dict,
    by_feed_id: dict[str, SourceArticleStats],
    by_name: dict[str, SourceArticleStats],
) -> SourceHealthItem:
    feed_id = str(feed.get("id") or "").strip()
    name = str(feed.get("title") or "").strip() or "Untitled feed"
    stats = _stats_for_feed(feed, by_feed_id, by_name)
    error_status, error_message = _error_status(feed)

    return SourceHealthItem(
        id=f"miniflux:{feed_id or _normalize_lookup_key(name)}",
        name=name,
        provider_label="Miniflux feed",
        feed_url=_safe_public_feed_url(feed.get("feed_url")),
        group=_category_title(feed),
        enabled=not bool(feed.get("disabled")),
        last_fetched_at=_parse_datetime(feed.get("checked_at")),
        recent_article_count=stats.count,
        error_status=error_status,
        error_message=error_message,
    )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw or raw.startswith("0001-01-01"):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fallback_items(by_name: dict[str, SourceArticleStats]) -> list[SourceHealthItem]:
    items: list[SourceHealthItem] = []
    for key, stats in sorted(by_name.items(), key=lambda item: (-item[1].count, item[0])):
        if not key or key == "unknown":
            continue
        name = stats.display_name or key.title()
        items.append(
            SourceHealthItem(
                id=f"publisher:{key}",
                name=name,
                provider_label="Roundup article publisher",
                feed_url=None,
                group=None,
                enabled=None,
                last_fetched_at=stats.last_fetched_at,
                recent_article_count=stats.count,
                error_status=None,
                error_message=None,
            )
        )
    return items


def build_source_list(session: Session, settings: Settings) -> SourceListResponse:
    by_feed_id, by_name = _recent_article_stats(session)
    fallback_items = _fallback_items(by_name)

    if not settings.has_miniflux_credentials:
        message = "Miniflux source metadata is not configured; showing recent article publishers when available."
        return SourceListResponse(
            provider="roundup",
            metadata_available=False,
            status="degraded" if fallback_items else "empty",
            message=message,
            total=len(fallback_items),
            items=fallback_items,
        )

    client = MinifluxClient(
        base_url=settings.miniflux_base_url,
        api_token=settings.miniflux_api_token_resolved,
        timeout_seconds=settings.miniflux_timeout_seconds,
    )

    try:
        feeds = client.fetch_feeds()
    except MinifluxClientError as exc:
        logger.warning("source_metadata_fetch_failed provider=miniflux error=%s", exc)
        return SourceListResponse(
            provider="miniflux",
            metadata_available=False,
            status="degraded" if fallback_items else "empty",
            message="Miniflux source metadata is unavailable; showing recent article publishers when available.",
            total=len(fallback_items),
            items=fallback_items,
        )

    items = [_item_from_miniflux_feed(feed, by_feed_id, by_name) for feed in feeds if isinstance(feed, dict)]
    items.sort(key=lambda item: ((item.group or "").casefold(), item.name.casefold(), item.id))
    message = "Configured Miniflux feeds with recent Roundup ingestion activity."
    return SourceListResponse(
        provider="miniflux",
        metadata_available=True,
        status="ok" if items else "empty",
        message=message if items else "No configured Miniflux feeds were returned.",
        total=len(items),
        items=items,
    )
