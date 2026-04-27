from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster
from app.services.clustering import cluster_new_articles
from app.services.ingestion import ingest_entries


def _entry(entry_id: int, title: str, url: str, published_at: str) -> dict:
    return {
        "id": entry_id,
        "title": title,
        "url": url,
        "published_at": published_at,
        "content": "Detailed report body",
        "feed": {"title": "Example Feed"},
        "author": "Reporter",
    }


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_api_token": "token",
        "cluster_min_sources_for_api": 1,
    }
    base.update(overrides)
    return Settings(**base)


def test_ingestion_deduplicates_identical_canonical_urls_within_batch(db_session: Session) -> None:
    entries = [
        _entry(1, "Transit Plan Update", "https://example.com/transit?utm_source=feed", "2026-04-22T10:00:00Z"),
        _entry(
            2,
            "Transit Expansion Plan Receives New Reactions",
            "https://example.com/transit?utm_source=newsletter",
            "2026-04-22T10:15:00Z",
        ),
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 1
    assert result.deduplicated == 1
    total = db_session.scalar(select(func.count()).select_from(Article))
    assert total == 1


def test_ingestion_allows_distinct_urls_with_similar_titles(db_session: Session) -> None:
    entries = [
        _entry(1, "Transit Plan Update", "https://example.com/transit-update-1", "2026-04-22T10:00:00Z"),
        _entry(2, "Transit Plan Update", "https://example.com/transit-update-2", "2026-04-22T10:05:00Z"),
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 2
    assert result.deduplicated == 0
    total = db_session.scalar(select(func.count()).select_from(Article))
    assert total == 2


def test_ingestion_deduplicates_against_existing_records(db_session: Session) -> None:
    first_batch = [_entry(1, "Budget Vote Scheduled", "https://example.com/budget", "2026-04-22T09:00:00Z")]
    second_batch = [
        _entry(2, "Budget Vote Brings New Commentary", "https://example.com/budget?utm_source=feed", "2026-04-22T09:30:00Z")
    ]

    first = ingest_entries(db_session, first_batch)
    db_session.commit()
    second = ingest_entries(db_session, second_batch)
    db_session.commit()

    assert first.ingested == 1
    assert second.ingested == 0
    assert second.deduplicated == 1


def test_ingestion_marks_blank_url_entry_as_malformed(db_session: Session) -> None:
    entries = [
        _entry(1, "Valid article", "https://example.com/valid", "2026-04-22T11:00:00Z"),
        _entry(2, "Broken article", "   ", "2026-04-22T11:05:00Z"),
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 1
    assert result.malformed == 1
    assert len(result.errors) == 1


def test_ingestion_persists_article_image_url_and_survives_malformed_image_metadata(db_session: Session) -> None:
    entries = [
        {
            **_entry(1, "Image story", "https://example.com/image-story", "2026-04-22T11:00:00Z"),
            "enclosures": [{"url": "https://cdn.example.com/story.jpg", "mime_type": "image/jpeg"}],
        },
        {
            **_entry(2, "No image story", "https://example.com/no-image-story", "2026-04-22T11:05:00Z"),
            "image": ["not", "a", "url"],
            "enclosures": {"url": "https://cdn.example.com/file.zip"},
        },
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 2
    articles = list(db_session.scalars(select(Article).order_by(Article.id.asc())).all())
    assert articles[0].image_url == "https://cdn.example.com/story.jpg"
    assert articles[1].image_url is None


def test_ingestion_rejects_service_finance_affiliate_and_stale_evergreen_items(db_session: Session) -> None:
    entries = [
        {
            **_entry(
                1,
                "Defense Secretary briefs NATO allies on ceasefire monitoring",
                "https://apnews.com/article/defense-nato-ceasefire",
                "2026-04-26T10:00:00Z",
            ),
            "feed": {"title": "AP Top News", "feed_url": "https://feeds.apnews.com/apnews/topnews"},
        },
        {
            **_entry(
                2,
                "Phoenix council approves emergency heat response funding",
                "https://kjzz.org/news/phoenix-heat-funding",
                "2026-04-26T10:05:00Z",
            ),
            "feed": {"title": "KJZZ", "feed_url": "https://kjzz.org/rss.xml"},
        },
        {
            **_entry(
                3,
                "Reuters: chipmaker shares fall after new export controls",
                "https://www.reuters.com/technology/chipmaker-export-controls",
                "2026-04-26T10:10:00Z",
            ),
            "feed": {
                "title": "Reuters Business",
                "feed_url": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
            },
        },
        _entry(
            4,
            "The 7 best high-yield savings accounts of April 2023",
            "https://example.com/best-high-yield-savings",
            "2026-04-26T10:15:00Z",
        ),
        _entry(
            5,
            "0% intro APR until 2024 is 100% insane",
            "https://example.com/zero-apr-card",
            "2026-04-26T10:20:00Z",
        ),
        _entry(
            6,
            "Turn Your Rising Home Equity Into Cash You Can Use",
            "https://example.com/home-equity-cash",
            "2026-04-26T10:25:00Z",
        ),
        _entry(
            7,
            "Best CD rates of March 2024",
            "https://example.com/cd-rates-2024",
            "2026-04-26T10:30:00Z",
        ),
        _entry(
            8,
            "Want Cash Out of Your Home? Here Are Your Best Options",
            "https://example.com/cash-out-home",
            "2026-04-26T10:35:00Z",
        ),
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 3
    assert result.rejected == 5
    stored_titles = set(db_session.scalars(select(Article.title)).all())
    assert "Defense Secretary briefs NATO allies on ceasefire monitoring" in stored_titles
    assert "Phoenix council approves emergency heat response funding" in stored_titles
    assert "Reuters: chipmaker shares fall after new export controls" in stored_titles
    assert "The 7 best high-yield savings accounts of April 2023" not in stored_titles
    assert "0% intro APR until 2024 is 100% insane" not in stored_titles
    assert "Turn Your Rising Home Equity Into Cash You Can Use" not in stored_titles
    assert "Want Cash Out of Your Home? Here Are Your Best Options" not in stored_titles

    cluster_new_articles(db_session, _settings())
    db_session.commit()

    cluster_titles = " ".join(db_session.scalars(select(Cluster.headline)).all())
    assert "high-yield savings" not in cluster_titles
    assert "intro APR" not in cluster_titles
    assert "Home Equity" not in cluster_titles
