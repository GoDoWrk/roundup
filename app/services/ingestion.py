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
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    errors: list[str] = []

    for index, entry in enumerate(entries):
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict):
                raise ValueError("entry is not an object")

            normalized = normalize_miniflux_entry(entry)
            if not normalized.canonical_url:
                raise ValueError("missing or blank url")

            if normalized.canonical_url in seen_urls:
                deduplicated += 1
                logger.info(
                    "ingest_article_deduplicated entry_index=%s entry_id=%r reason=duplicate_url_in_batch canonical_url=%s dedupe_hash=%s",
                    index,
                    entry_id,
                    normalized.canonical_url,
                    normalized.dedupe_hash,
                )
                continue

            existing_url_article_id = session.scalar(
                select(Article.id).where(Article.canonical_url == normalized.canonical_url)
            )
            if existing_url_article_id:
                deduplicated += 1
                logger.info(
                    "ingest_article_deduplicated entry_index=%s entry_id=%r reason=duplicate_url_existing existing_article_id=%s canonical_url=%s dedupe_hash=%s",
                    index,
                    entry_id,
                    existing_url_article_id,
                    normalized.canonical_url,
                    normalized.dedupe_hash,
                )
                continue

            if normalized.dedupe_hash in seen_hashes:
                deduplicated += 1
                logger.info(
                    "ingest_article_deduplicated entry_index=%s entry_id=%r reason=duplicate_hash_in_batch canonical_url=%s dedupe_hash=%s",
                    index,
                    entry_id,
                    normalized.canonical_url,
                    normalized.dedupe_hash,
                )
                continue

            existing_hash_article_id = session.scalar(
                select(Article.id).where(Article.dedupe_hash == normalized.dedupe_hash)
            )
            if existing_hash_article_id:
                deduplicated += 1
                logger.info(
                    "ingest_article_deduplicated entry_index=%s entry_id=%r reason=duplicate_hash_existing existing_article_id=%s canonical_url=%s dedupe_hash=%s",
                    index,
                    entry_id,
                    existing_hash_article_id,
                    normalized.canonical_url,
                    normalized.dedupe_hash,
                )
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
                topic=normalized.topic,
                dedupe_hash=normalized.dedupe_hash,
            )
            session.add(article)
            session.flush()
            seen_urls.add(normalized.canonical_url)
            seen_hashes.add(normalized.dedupe_hash)
            ingested += 1
            inserted.append(normalized)
            logger.info(
                "ingest_article_inserted entry_index=%s entry_id=%r article_id=%s canonical_url=%s dedupe_hash=%s",
                index,
                entry_id,
                article.id,
                normalized.canonical_url,
                normalized.dedupe_hash,
            )
        except Exception as exc:
            malformed += 1
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
