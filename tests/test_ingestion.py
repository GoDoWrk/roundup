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


def test_ingestion_deduplicates_identical_entries_within_batch(db_session: Session) -> None:
    entries = [
        _entry(1, "Transit Plan Update", "https://example.com/transit", "2026-04-22T10:00:00Z"),
        _entry(2, "Transit Plan Update", "https://example.com/transit", "2026-04-22T10:00:00Z"),
    ]

    result = ingest_entries(db_session, entries)
    db_session.commit()

    assert result.ingested == 1
    assert result.deduplicated == 1
    total = db_session.scalar(select(func.count()).select_from(Article))
    assert total == 1


def test_ingestion_deduplicates_against_existing_records(db_session: Session) -> None:
    first_batch = [_entry(1, "Budget Vote Scheduled", "https://example.com/budget", "2026-04-22T09:00:00Z")]
    second_batch = [_entry(2, "Budget Vote Scheduled", "https://example.com/budget", "2026-04-22T09:00:00Z")]

    first = ingest_entries(db_session, first_batch)
    db_session.commit()
    second = ingest_entries(db_session, second_batch)
    db_session.commit()

    assert first.ingested == 1
    assert second.ingested == 0
    assert second.deduplicated == 1
