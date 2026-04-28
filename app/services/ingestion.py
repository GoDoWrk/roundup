from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Article
from app.services.content_quality import classify_article_content, evaluate_normalized_article_quality
from app.services.normalizer import NormalizedArticle, normalize_miniflux_entry
from app.services.topics import classify_topic_from_text

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    ingested: int
    deduplicated: int
    malformed: int
    rejected: int
    rejected_stale: int
    rejected_service_finance: int
    normalized: list[NormalizedArticle]
    errors: list[str]


def ingest_entries(session: Session, entries: list[dict]) -> IngestResult:
    ingested = 0
    deduplicated = 0
    malformed = 0
    rejected = 0
    rejected_stale = 0
    rejected_service_finance = 0
    inserted: list[NormalizedArticle] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    errors: list[str] = []
    prepared_entries: list[tuple[int, object, NormalizedArticle, object]] = []

    for index, entry in enumerate(entries):
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        try:
            if not isinstance(entry, dict):
                raise ValueError("entry is not an object")

            normalized = normalize_miniflux_entry(entry)
            if not normalized.canonical_url:
                raise ValueError("missing or blank url")

            quality = evaluate_normalized_article_quality(normalized)
            classification = classify_article_content(
                title=normalized.title,
                url=normalized.url,
                publisher=normalized.publisher,
                content_text=normalized.content_text,
                raw_payload=normalized.raw_payload,
                source_trust=quality.source_trust,
            )
            topic_classification = classify_topic_from_text(
                normalized.title,
                f"{normalized.publisher} {normalized.content_text}",
                keywords=normalized.keywords,
                entities=normalized.entities,
            )
            if quality.action == "reject":
                rejected += 1
                if "stale_content" in quality.reasons:
                    rejected_stale += 1
                if "affiliate_finance" in quality.reasons:
                    rejected_service_finance += 1
                logger.info(
                    "ingest_article_rejected entry_index=%s entry_id=%r reasons=%s source_trust=%s "
                    "priority=%s promote_to_home=%s canonical_url=%s title=%r",
                    index,
                    entry_id,
                    ",".join(quality.reasons),
                    quality.source_trust,
                    quality.source_controls.priority,
                    quality.source_controls.promote_to_home,
                    normalized.canonical_url,
                    normalized.title,
                )
                continue

            prepared_entries.append((index, entry_id, normalized, topic_classification))
            metadata = dict(normalized.raw_payload.get("__roundup", {})) if isinstance(normalized.raw_payload, dict) else {}
            metadata.update(
                {
                    "content_class": classification.content_class,
                    "classification_reasons": list(classification.reasons),
                    "primary_entities": list(classification.primary_entities),
                    "secondary_entities": list(classification.secondary_entities),
                    "quality_reasons": list(quality.reasons),
                    "source_trust": quality.source_trust,
                    "primary_topic": topic_classification.primary_topic,
                    "subtopic": topic_classification.subtopic,
                    "key_entities": list(topic_classification.key_entities),
                    "geography": topic_classification.geography,
                    "event_type": topic_classification.event_type,
                }
            )
            normalized.raw_payload["__roundup"] = metadata
        except Exception as exc:
            malformed += 1
            message = f"entry_index={index} entry_id={entry_id!r} error={exc}"
            errors.append(message)
            logger.warning("ingest_entry_skipped_malformed %s", message)

    if not prepared_entries:
        return IngestResult(
            ingested=ingested,
            deduplicated=deduplicated,
            malformed=malformed,
            rejected=rejected,
            rejected_stale=rejected_stale,
            rejected_service_finance=rejected_service_finance,
            normalized=inserted,
            errors=errors,
        )

    canonical_urls = {normalized.canonical_url for _, _, normalized, _ in prepared_entries}
    dedupe_hashes = {normalized.dedupe_hash for _, _, normalized, _ in prepared_entries}

    existing_url_article_ids = {
        canonical_url: article_id
        for canonical_url, article_id in session.execute(
            select(Article.canonical_url, func.min(Article.id)).where(Article.canonical_url.in_(canonical_urls)).group_by(
                Article.canonical_url
            )
        ).all()
    }
    existing_hash_article_ids = {
        dedupe_hash: article_id
        for dedupe_hash, article_id in session.execute(
            select(Article.dedupe_hash, func.min(Article.id)).where(Article.dedupe_hash.in_(dedupe_hashes)).group_by(
                Article.dedupe_hash
            )
        ).all()
    }

    for index, entry_id, normalized, topic_classification in prepared_entries:
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

        existing_url_article_id = existing_url_article_ids.get(normalized.canonical_url)
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

        existing_hash_article_id = existing_hash_article_ids.get(normalized.dedupe_hash)
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
            image_url=normalized.image_url,
            raw_payload=normalized.raw_payload,
            normalized_title=normalized.normalized_title,
            keywords=normalized.keywords,
            entities=normalized.entities,
            topic=normalized.topic,
            primary_topic=topic_classification.primary_topic,
            subtopic=topic_classification.subtopic,
            key_entities=list(topic_classification.key_entities),
            geography=topic_classification.geography,
            event_type=topic_classification.event_type,
            dedupe_hash=normalized.dedupe_hash,
        )
        try:
            with session.begin_nested():
                session.add(article)
                session.flush()
        except IntegrityError as exc:
            deduplicated += 1
            logger.warning(
                "ingest_article_deduplicated entry_index=%s entry_id=%r reason=integrity_conflict canonical_url=%s dedupe_hash=%s error=%s",
                index,
                entry_id,
                normalized.canonical_url,
                normalized.dedupe_hash,
                exc.orig,
            )
            continue
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

    return IngestResult(
        ingested=ingested,
        deduplicated=deduplicated,
        malformed=malformed,
        rejected=rejected,
        rejected_stale=rejected_stale,
        rejected_service_finance=rejected_service_finance,
        normalized=inserted,
        errors=errors,
    )
