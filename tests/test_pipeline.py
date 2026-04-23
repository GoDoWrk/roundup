from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, PipelineStats
from app.services.miniflux_client import MinifluxRequestError
from app.services.pipeline import run_pipeline


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_base_url": "http://miniflux.local",
        "miniflux_api_token": "token",
        "sample_miniflux_data_path": str(tmp_path / "sample.json"),
        "cluster_min_sources_for_api": 1,
    }
    base.update(overrides)
    return Settings(**base)


def _sample_entries() -> list[dict]:
    return [
        {
            "id": 1,
            "title": "City Council Approves Transit Plan",
            "url": "https://example.com/transit",
            "published_at": "2026-04-22T10:00:00Z",
            "content": "Update",
            "feed": {"title": "Example Feed"},
        }
    ]


def test_pipeline_handles_zero_new_articles(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", lambda self, limit: [])

    result = run_pipeline(db_session, settings, run_id="zero")

    assert result.fetched == 0
    assert result.ingested == 0
    assert result.deduplicated == 0
    assert result.malformed == 0


def test_pipeline_falls_back_to_sample_data_when_miniflux_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(_sample_entries()), encoding="utf-8")
    settings = _settings(tmp_path, sample_miniflux_data_path=str(sample_path))

    def _raise(self, limit: int):
        raise MinifluxRequestError("boom")

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", _raise)

    result = run_pipeline(db_session, settings, run_id="fallback")

    assert result.ingestion_source == "sample_fallback"
    assert result.fetched == 1
    assert result.ingested == 1

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.ingest_source_failures_total >= 1


def test_pipeline_skips_malformed_entry_and_ingests_rest(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    entries = [
        {
            "id": 1,
            "title": "Valid entry",
            "url": "https://example.com/valid",
            "published_at": "2026-04-22T10:00:00Z",
            "content": "Body",
            "feed": {"title": "Feed"},
        },
        {
            "id": 2,
            "title": "Bad entry",
            "url": "https://example.com/bad",
            "published_at": "not-a-date",
            "content": "Body",
            "feed": {"title": "Feed"},
        },
    ]

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", lambda self, limit: entries)

    result = run_pipeline(db_session, settings, run_id="malformed")

    assert result.fetched == 2
    assert result.ingested == 1
    assert result.malformed == 1

    article_count = db_session.scalar(select(func.count()).select_from(Article))
    assert article_count == 1

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.articles_malformed_total >= 1


def test_pipeline_survives_miniflux_failure_without_sample(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path, sample_miniflux_data_path=None)

    def _raise(self, limit: int):
        raise MinifluxRequestError("unavailable")

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", _raise)

    result = run_pipeline(db_session, settings, run_id="source-error")

    assert result.ingestion_source == "miniflux_error"
    assert result.fetched == 0
    assert result.ingested == 0

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.ingest_source_failures_total >= 1
