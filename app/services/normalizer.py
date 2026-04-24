from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.services.topics import derive_topic_from_text

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "against",
    "among",
    "because",
    "before",
    "being",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
    "just",
    "many",
    "more",
    "most",
    "news",
    "over",
    "said",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "were",
    "with",
    "would",
}


@dataclass(frozen=True)
class NormalizedArticle:
    external_id: str
    title: str
    url: str
    canonical_url: str
    publisher: str
    published_at: datetime
    content_text: str
    raw_payload: dict
    normalized_title: str
    keywords: list[str]
    entities: list[str]
    topic: str
    dedupe_hash: str


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_pairs = [(k, v) for k, v in query_pairs if not k.lower().startswith("utm_")]
    canonical_query = urlencode(filtered_pairs)
    canonical = parsed._replace(query=canonical_query, fragment="")
    return urlunparse(canonical)


def normalize_title(value: str) -> str:
    compact = normalize_whitespace(value).lower()
    return re.sub(r"[^a-z0-9\s]", "", compact)


def extract_keywords(text: str, max_keywords: int = 12) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:max_keywords]]


def extract_entities(text: str, max_entities: int = 12) -> list[str]:
    matches = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)
    compact = [normalize_whitespace(m) for m in matches]
    unique_sorted = sorted(set(compact))
    return unique_sorted[:max_entities]


def parse_published_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    raw = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_dedupe_hash(canonical_url: str, normalized_title_value: str, published_at: datetime) -> str:
    daily_bucket = published_at.astimezone(timezone.utc).date().isoformat()
    payload = f"{canonical_url}|{normalized_title_value}|{daily_bucket}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_miniflux_entry(entry: dict) -> NormalizedArticle:
    title = normalize_whitespace(str(entry.get("title") or "Untitled article"))
    url = normalize_whitespace(str(entry.get("url") or ""))
    canonical_url = canonicalize_url(url)

    content = normalize_whitespace(str(entry.get("content") or ""))
    publisher = normalize_whitespace(
        str((entry.get("feed") or {}).get("title") or entry.get("author") or "unknown")
    )
    published_at = parse_published_at(entry.get("published_at"))

    normalized_title_value = normalize_title(title)
    keyword_text = f"{title} {content[:2000]}"
    keywords = extract_keywords(keyword_text)
    entities = extract_entities(keyword_text)
    topic = derive_topic_from_text(title, content)

    dedupe_hash = build_dedupe_hash(canonical_url, normalized_title_value, published_at)

    return NormalizedArticle(
        external_id=str(entry.get("id") or ""),
        title=title,
        url=url,
        canonical_url=canonical_url,
        publisher=publisher or "unknown",
        published_at=published_at,
        content_text=content[:10000],
        raw_payload=entry,
        normalized_title=normalized_title_value,
        keywords=keywords,
        entities=entities,
        topic=topic,
        dedupe_hash=dedupe_hash,
    )
