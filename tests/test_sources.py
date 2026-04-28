from __future__ import annotations

from datetime import datetime, timedelta, timezone
import socket

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Article
from app.main import app
from app.services.miniflux_client import MinifluxRequestError


def _mock_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if str(host).rstrip(".").lower() == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_base_url": "http://miniflux.local",
        "miniflux_api_token": "token",
        "miniflux_api_token_file": None,
        "sample_miniflux_data_path": None,
    }
    base.update(overrides)
    return Settings(**base)


def _use_settings(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


def _article(
    idx: int,
    now: datetime,
    *,
    publisher: str = "Example Feed",
    feed: dict | None = None,
    fetched_at: datetime | None = None,
) -> Article:
    return Article(
        external_id=str(idx),
        title=f"Article {idx}",
        url=f"https://example.com/article-{idx}",
        canonical_url=f"https://example.com/article-{idx}",
        publisher=publisher,
        published_at=now - timedelta(hours=idx),
        fetched_at=fetched_at or now,
        content_text="Body",
        image_url=None,
        raw_payload={"id": idx, "feed": feed or {"id": 42, "title": publisher}},
        normalized_title=f"article {idx}",
        keywords=["article"],
        entities=["Example"],
        topic="general",
        dedupe_hash=f"source-article-{idx}",
    )


def test_sources_endpoint_returns_miniflux_metadata_and_article_counts(
    client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_public_dns(monkeypatch)
    now = datetime.now(timezone.utc)
    db_session.add(_article(1, now, publisher="Example Feed", feed={"id": 42, "title": "Example Feed"}))
    db_session.commit()
    _use_settings(_settings())

    monkeypatch.setattr(
        "app.services.sources.MinifluxClient.fetch_feeds",
        lambda self: [
            {
                "id": 42,
                "title": "Example Feed",
                "feed_url": "https://example.com/feed.xml",
                "checked_at": "2026-04-25T12:00:00Z",
                "disabled": False,
                "parsing_error_message": "",
                "parsing_error_count": 0,
                "category": {"title": "World News"},
                "username": "do-not-return",
                "password": "do-not-return",
            }
        ],
    )

    response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "miniflux"
    assert payload["metadata_available"] is True
    assert payload["status"] == "ok"
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["name"] == "Example Feed"
    assert item["feed_url"] == "https://example.com/feed.xml"
    assert item["group"] == "World News"
    assert item["enabled"] is True
    assert item["last_fetched_at"] == "2026-04-25T12:00:00Z"
    assert item["recent_article_count"] == 1
    assert item["error_status"] == "ok"
    assert "username" not in item
    assert "password" not in item


def test_sources_endpoint_sanitizes_unsafe_feed_urls(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(_settings())
    monkeypatch.setattr(
        "app.services.sources.MinifluxClient.fetch_feeds",
        lambda self: [
            {
                "id": 1,
                "title": "Private Feed",
                "feed_url": "https://user:secret@example.com/feed.xml",
                "checked_at": None,
                "disabled": False,
            },
            {
                "id": 2,
                "title": "Token Feed",
                "feed_url": "https://example.com/feed.xml?token=secret",
                "checked_at": None,
                "disabled": False,
            },
            {
                "id": 3,
                "title": "Metadata Feed",
                "feed_url": "http://169.254.169.254/latest/meta-data",
                "checked_at": None,
                "disabled": False,
            },
        ],
    )

    response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert [item["feed_url"] for item in payload["items"]] == [None, None, None]
    assert {item["provider_label"] for item in payload["items"]} == {"Miniflux feed"}


def test_sources_endpoint_falls_back_to_recent_publishers_when_miniflux_unavailable(
    client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(_article(1, now, publisher="Fallback Publisher", feed={"title": "Fallback Publisher"}))
    db_session.commit()
    _use_settings(_settings())

    def _raise(self):
        raise MinifluxRequestError("unavailable")

    monkeypatch.setattr("app.services.sources.MinifluxClient.fetch_feeds", _raise)

    response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "miniflux"
    assert payload["metadata_available"] is False
    assert payload["status"] == "degraded"
    assert payload["items"][0]["name"] == "Fallback Publisher"
    assert payload["items"][0]["recent_article_count"] == 1
    assert payload["items"][0]["enabled"] is None


def test_sources_endpoint_handles_missing_metadata_and_no_articles(client) -> None:
    _use_settings(_settings(miniflux_api_token="", miniflux_api_token_file=None))

    response = client.get("/api/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "roundup"
    assert payload["metadata_available"] is False
    assert payload["status"] == "empty"
    assert payload["total"] == 0
    assert payload["items"] == []
