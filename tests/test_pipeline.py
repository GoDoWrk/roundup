from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, PipelineStats
from app.services.ingestion import ingest_entries
from app.services.miniflux_client import MinifluxRequestError
from app.services.pipeline import run_pipeline
from scripts.run_pipeline_once import reset_sample_mode_state_if_needed


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_base_url": "http://miniflux.local",
        "miniflux_api_token": "token",
        "demo_mode": False,
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


def _sample_three_entries() -> list[dict]:
    return [
        {
            "id": 1001,
            "title": "City Council Approves Transit Expansion Plan",
            "url": "https://example.com/news/transit-expansion",
            "published_at": "2026-04-22T12:00:00Z",
            "content": "City Council approved a transit expansion proposal and released funding details.",
            "feed": {"title": "Metro Daily"},
            "author": "Reporter A",
        },
        {
            "id": 1002,
            "title": "Regional Leaders React to Transit Expansion Funding",
            "url": "https://example.com/news/transit-funding-reaction",
            "published_at": "2026-04-22T14:30:00Z",
            "content": "Regional transportation leaders responded to the approved transit expansion funding package.",
            "feed": {"title": "Regional Wire"},
            "author": "Reporter B",
        },
        {
            "id": 1003,
            "title": "Transit Agencies Publish First Implementation Timeline",
            "url": "https://example.com/news/transit-timeline",
            "published_at": "2026-04-22T17:10:00Z",
            "content": "Transit agencies published expected implementation milestones after the vote.",
            "feed": {"title": "Transport Bulletin"},
            "author": "Reporter C",
        },
    ]


def test_pipeline_handles_zero_new_articles(db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", lambda self, limit: [])

    result = run_pipeline(db_session, settings, run_id="zero")

    assert result.fetched == 0
    assert result.ingested == 0
    assert result.deduplicated == 0
    assert result.malformed == 0


def test_pipeline_does_not_fallback_to_sample_when_miniflux_is_configured(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(_sample_entries()), encoding="utf-8")
    settings = _settings(tmp_path, sample_miniflux_data_path=str(sample_path))

    def _raise(self, limit: int):
        raise MinifluxRequestError("boom")

    monkeypatch.setattr("app.services.miniflux_client.MinifluxClient.fetch_entries", _raise)

    result = run_pipeline(db_session, settings, run_id="miniflux-failure")

    assert result.ingestion_source == "miniflux_error"
    assert result.fetched == 0
    assert result.ingested == 0

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.ingest_source_failures_total >= 1


def test_pipeline_uses_sample_source_when_miniflux_not_configured(db_session: Session, tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(_sample_entries()), encoding="utf-8")
    settings = _settings(
        tmp_path,
        miniflux_api_token="",
        demo_mode=True,
        sample_miniflux_data_path=str(sample_path),
    )

    result = run_pipeline(db_session, settings, run_id="sample-only")

    assert result.ingestion_source == "sample"
    assert result.fetched == 1
    assert result.ingested == 1


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
    article = db_session.scalars(select(Article)).first()
    assert article is not None
    assert article.title == "Valid entry"
    assert article.url == "https://example.com/valid"
    assert article.publisher == "Feed"
    assert article.published_at.isoformat().startswith("2026-04-22T10:00:00")

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.articles_malformed_total >= 1
    assert stats.latest_articles_fetched == 2
    assert stats.latest_articles_stored == 1
    assert stats.latest_duplicate_articles_skipped == 0
    assert stats.latest_articles_malformed == 1
    assert stats.latest_failed_source_count == 0


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


def test_sample_mode_reset_removes_only_sample_articles_and_reingests(
    db_session: Session, tmp_path: Path
) -> None:
    sample_entries = _sample_three_entries()
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(sample_entries), encoding="utf-8")

    settings = _settings(
        tmp_path,
        miniflux_api_token="",
        demo_mode=True,
        sample_miniflux_data_path=str(sample_path),
        cluster_min_sources_for_api=3,
    )

    unrelated_entry = {
        "id": 4001,
        "title": "Unrelated Coverage",
        "url": "https://example.com/news/unrelated",
        "published_at": "2026-04-22T08:00:00Z",
        "content": "Separate story that should not be cleared by sample reset.",
        "feed": {"title": "Independent Desk"},
    }
    ingest_entries(db_session, sample_entries + [unrelated_entry])
    now = datetime.now(timezone.utc)
    db_session.add(
        Cluster(
            id="orphan-cluster",
            headline="Orphan cluster",
            summary="Orphan summary with sufficient words to satisfy validation checks.",
            what_changed="Orphan details changed and remained disconnected from source links.",
            why_it_matters="Orphan impact remains isolated and should be pruned during sample reset.",
            first_seen=now,
            last_updated=now,
            score=0.1,
            status="emerging",
            normalized_headline="orphan cluster",
            keywords=["orphan"],
            entities=[],
        )
    )
    db_session.commit()

    reset_sample_mode_state_if_needed(db_session, settings)
    db_session.commit()

    remaining_urls = set(db_session.scalars(select(Article.canonical_url)).all())
    assert "https://example.com/news/unrelated" in remaining_urls
    assert "https://example.com/news/transit-expansion" not in remaining_urls
    assert db_session.get(Cluster, "orphan-cluster") is None

    result = run_pipeline(db_session, settings, run_id="sample-reset")

    assert result.ingested > 0
    assert result.clusters_created > 0
