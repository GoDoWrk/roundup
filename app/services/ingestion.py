from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article
from app.services.normalizer import NormalizedArticle, normalize_miniflux_entry


@dataclass
class IngestResult:
    ingested: int
    deduplicated: int
    normalized: list[NormalizedArticle]


def ingest_entries(session: Session, entries: list[dict]) -> IngestResult:
    ingested = 0
    deduplicated = 0
    inserted: list[NormalizedArticle] = []

    for entry in entries:
        normalized = normalize_miniflux_entry(entry)
        exists = session.scalar(select(Article.id).where(Article.dedupe_hash == normalized.dedupe_hash))
        if exists:
            deduplicated += 1
            continue

        article = Article(
            external_id=normalized.external_id or None,
            title=normalized.title,
            url=normalized.url,
            canonical_url=normalized.canonical_url,
            publisher=normalized.publisher,
            published_at=normalized.published_at,
            content_text=normalized.content_text,
            raw_payload=normalized.raw_payload,
            normalized_title=normalized.normalized_title,
            keywords=normalized.keywords,
            entities=normalized.entities,
            dedupe_hash=normalized.dedupe_hash,
        )
        session.add(article)
        ingested += 1
        inserted.append(normalized)

    return IngestResult(ingested=ingested, deduplicated=deduplicated, normalized=inserted)
