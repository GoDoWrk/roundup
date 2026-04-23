from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Article
from app.services.normalizer import NormalizedArticle, normalize_miniflux_entry

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    ingested: int
    deduplicated: int
    malformed: int
    normalized: list[NormalizedArticle]
    errors: list[str]


def ingest_entries(session: Session, entries: list[dict]) -> IngestResult:
    ingested = 0
    deduplicated = 0
    malformed = 0
    inserted: list[NormalizedArticle] = []
    seen_hashes: set[str] = set()
    errors: list[str] = []

    for index, entry in enumerate(entries):
        try:
            if not isinstance(entry, dict):
                raise ValueError("entry is not an object")

            normalized = normalize_miniflux_entry(entry)
            if normalized.dedupe_hash in seen_hashes:
                deduplicated += 1
                continue

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
            seen_hashes.add(normalized.dedupe_hash)
            ingested += 1
            inserted.append(normalized)
        except Exception as exc:
            malformed += 1
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            message = f"entry_index={index} entry_id={entry_id!r} error={exc}"
            errors.append(message)
            logger.warning("ingest_entry_skipped_malformed %s", message)

    return IngestResult(
        ingested=ingested,
        deduplicated=deduplicated,
        malformed=malformed,
        normalized=inserted,
        errors=errors,
    )
