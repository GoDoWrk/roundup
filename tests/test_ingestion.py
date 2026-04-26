from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Article
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
