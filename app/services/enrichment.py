from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.db.models import Article
from app.services.normalizer import normalize_title


@dataclass(frozen=True)
class TimelineEntry:
    timestamp: datetime
    event: str
    source_url: str
    source_title: str


def _fallback_text(prefix: str, topic: str) -> str:
    return f"{prefix} around {topic}."


def _topic_from_articles(articles: list[Article]) -> str:
    entities = _top_terms(articles, attr="entities", limit=3, min_count=2)
    if entities:
        return entities[0]
    keywords = _top_terms(articles, attr="keywords", limit=3, min_count=2)
    if keywords:
        return keywords[0]
    keywords = _top_terms(articles, attr="keywords", limit=3, min_count=1)
    return keywords[0] if keywords else "a developing story"


def _top_terms(articles: list[Article], *, attr: str, limit: int, min_count: int) -> list[str]:
    counter: Counter[str] = Counter()
    for article in articles:
        terms = {str(term).strip() for term in getattr(article, attr, []) if str(term).strip()}
        counter.update(terms)

    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    filtered = [term for term, count in ranked if count >= min_count]
    if filtered:
        return filtered[:limit]
    return [term for term, _ in ranked[:limit]]


def _representative_article(articles: list[Article]) -> Article | None:
    if not articles:
        return None
    shared_entities = set(_top_terms(articles, attr="entities", limit=5, min_count=2))
    shared_keywords = set(_top_terms(articles, attr="keywords", limit=5, min_count=2))

    def score(article: Article) -> tuple[float, datetime, int]:
        entity_hits = sum(1 for entity in article.entities if entity in shared_entities)
        keyword_hits = sum(1 for keyword in article.keywords if keyword in shared_keywords)
        title_weight = min(len((article.title or "").strip()), 120) / 120
        return (entity_hits * 2 + keyword_hits + title_weight, article.published_at, article.id)

    return max(articles, key=score)


def build_headline(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("Developing coverage", "a new cluster")

    representative = _representative_article(articles)
    if representative is not None:
        title = (representative.title or "").strip()
        if len(title.split()) >= 3 and normalize_title(title) not in {"untitled article", "update"}:
            return title

    topic = _topic_from_articles(articles)
    return _fallback_text("Developing coverage", topic)


def build_summary(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("Coverage is still forming", "a new cluster")

    publishers = sorted({a.publisher for a in articles if a.publisher})
    earliest = min(a.published_at for a in articles)
    latest = max(a.published_at for a in articles)
    span_hours = max(0, int((latest - earliest).total_seconds() // 3600))

    entities = _top_terms(articles, attr="entities", limit=3, min_count=2)
    keywords = _top_terms(articles, attr="keywords", limit=4, min_count=2)
    topic_bits = entities + [keyword for keyword in keywords if keyword not in entities]

    source_text = ", ".join(publishers[:3]) if publishers else "multiple publishers"
    topic_text = ", ".join(topic_bits[:4]) if topic_bits else _topic_from_articles(articles)

    return (
        f"{len(articles)} sources, including {source_text}, are covering {topic_text}. "
        f"Reporting has evolved across a {span_hours}-hour window."
    )


def build_what_changed(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("No changes are available", "this story")

    ordered = sorted(articles, key=lambda a: (a.published_at, a.id))
    first = ordered[0]
    latest = ordered[-1]

    if len(ordered) == 1:
        topic = _topic_from_articles(ordered)
        return f"Initial reporting from {first.publisher} established early coverage focused on {topic}."

    first_terms = set(first.entities + first.keywords)
    latest_terms = set(latest.entities + latest.keywords)
    newly_seen_terms = sorted(latest_terms - first_terms)[:3]
    new_term_text = ", ".join(newly_seen_terms) if newly_seen_terms else "additional confirmed details"

    new_publishers = sorted({a.publisher for a in ordered[1:] if a.publisher and a.publisher != first.publisher})
    publisher_delta = ", ".join(new_publishers[:2]) if new_publishers else "follow-up reporting"

    return (
        f"Coverage moved from the initial report by {first.publisher} to broader updates from {publisher_delta}. "
        f"Recent articles introduced {new_term_text}."
    )


def build_why_it_matters(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("Impact remains unclear", "this developing event")

    earliest = min(a.published_at for a in articles)
    latest = max(a.published_at for a in articles)
    span_hours = max(0, int((latest - earliest).total_seconds() // 3600))
    publishers = {a.publisher for a in articles if a.publisher}
    topic = _topic_from_articles(articles)

    return (
        f"This matters because {len(publishers) or 1} publishers kept updating {topic} over {span_hours} hours, "
        "which indicates sustained relevance and continuing developments."
    )


def build_timeline_events(
    articles: list[Article],
    *,
    dedupe_window_hours: int,
    dedupe_title_similarity: float,
) -> tuple[list[TimelineEntry], int]:
    ordered = sorted(articles, key=lambda a: (a.published_at, a.id))
    if not ordered:
        return [], 0

    timeline_with_meta: list[dict] = []
    deduplicated_count = 0
    seen_publishers: set[str] = set()
    seen_terms: set[str] = set()

    for article in ordered:
        title = (article.title or "").strip() or "Untitled update"
        publisher = article.publisher or "unknown"
        normalized = article.normalized_title or normalize_title(title)

        duplicate = False
        for prior in reversed(timeline_with_meta):
            if prior["publisher"] != publisher:
                continue
            delta_hours = abs((article.published_at - prior["timestamp"]).total_seconds()) / 3600
            if delta_hours > max(dedupe_window_hours, 0):
                continue
            similarity = SequenceMatcher(None, normalized, prior["normalized_title"]).ratio()
            containment_match = normalized in prior["normalized_title"] or prior["normalized_title"] in normalized
            if similarity >= dedupe_title_similarity or containment_match:
                duplicate = True
                break

        if duplicate:
            deduplicated_count += 1
            continue

        fresh_terms = [term for term in (article.entities + article.keywords) if term and term not in seen_terms]
        topic_delta = ", ".join(fresh_terms[:3])

        if publisher not in seen_publishers:
            event_text = f"{publisher} added coverage: {title}"
        elif topic_delta:
            event_text = f"{publisher} reported new details on {topic_delta}."
        else:
            event_text = f"{publisher} published a follow-up update."

        timeline_with_meta.append(
            {
                "timestamp": article.published_at,
                "event": event_text,
                "source_url": article.url,
                "source_title": article.title,
                "publisher": publisher,
                "normalized_title": normalized,
            }
        )

        seen_publishers.add(publisher)
        seen_terms.update(term for term in article.entities + article.keywords if term)

    timeline = [
        TimelineEntry(
            timestamp=row["timestamp"],
            event=row["event"],
            source_url=row["source_url"],
            source_title=row["source_title"],
        )
        for row in timeline_with_meta
    ]
    return timeline, deduplicated_count


def build_status(
    source_count: int,
    last_updated: datetime,
    now: datetime,
    stale_hours: int,
    emerging_hours: int,
    emerging_source_count: int,
) -> str:
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    hours_since_update = (now - last_updated).total_seconds() / 3600
    if hours_since_update >= stale_hours:
        return "stale"
    if source_count < emerging_source_count and hours_since_update <= emerging_hours:
        return "emerging"
    return "active"
