from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from app.db.models import Article
from app.services.normalizer import NormalizedArticle, canonicalize_url, normalize_whitespace

logger = logging.getLogger(__name__)

SourcePriority = Literal["high", "normal", "low"]
SourceTrust = Literal["high", "normal", "low"]
QualityAction = Literal["accept", "reject"]
ContentClass = Literal[
    "hard_news",
    "politics",
    "local_news",
    "business_news",
    "service_finance",
    "evergreen",
    "opinion",
    "sports",
    "entertainment",
    "official_release",
    "low_trust_aggregator",
    "unknown",
]

FINANCE_SERVICE_PATTERNS = (
    re.compile(r"\bbest\s+credit\s+cards?\b", re.IGNORECASE),
    re.compile(r"\bhigh[-\s]?yield\s+savings\b", re.IGNORECASE),
    re.compile(r"\bsavings\s+accounts?\b", re.IGNORECASE),
    re.compile(r"\bcd\s+rates?\b", re.IGNORECASE),
    re.compile(r"\bmortgage\s+rates?\b", re.IGNORECASE),
    re.compile(r"\bhome\s+equity\b", re.IGNORECASE),
    re.compile(r"\bcash\s+out\s+of\s+(?:your\s+)?home\b", re.IGNORECASE),
    re.compile(r"\bhome\b.{0,60}\bcash\b|\bcash\b.{0,60}\bhome\b", re.IGNORECASE),
    re.compile(r"\bpersonal\s+loans?\b", re.IGNORECASE),
    re.compile(r"\bdebt\s+relief\b", re.IGNORECASE),
    re.compile(r"\binsurance\s+quotes?\b", re.IGNORECASE),
    re.compile(r"\bintro\s+apr\b", re.IGNORECASE),
    re.compile(r"\b0%\s+intro\s+apr\b", re.IGNORECASE),
    re.compile(r"\brefinanc(?:e|ing)\b", re.IGNORECASE),
)

SERVICE_JOURNALISM_PATTERNS = (
    re.compile(r"\bbest\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+best\b", re.IGNORECASE),
    re.compile(r"\btop\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+ways\b", re.IGNORECASE),
    re.compile(r"\b\d+\+?\s+(?:useful\s+)?products?\b", re.IGNORECASE),
    re.compile(r"\bways\s+to\s+save\b", re.IGNORECASE),
    re.compile(r"\bsave\s+you\s+money\b", re.IGNORECASE),
    re.compile(r"\byou\s+can\s+use\b", re.IGNORECASE),
    re.compile(r"\byou\s+can\s+buy\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\b", re.IGNORECASE),
    re.compile(r"\beasy\s+way\s+to\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+to\s+use\s+instead\b", re.IGNORECASE),
    re.compile(r"\bmake\s+your\s+life\s+easier\b", re.IGNORECASE),
    re.compile(r"\bhow\s+to\s+file\b", re.IGNORECASE),
    re.compile(r"\bgifts?\s+(?:she|he|they|you)'?ll\s+love\b", re.IGNORECASE),
    re.compile(r"\bguide\s+of\s+how\b", re.IGNORECASE),
    re.compile(r"\bsponsored\b", re.IGNORECASE),
    re.compile(r"\bpartner\s+offer\b", re.IGNORECASE),
    re.compile(r"\baffiliate\b", re.IGNORECASE),
    re.compile(r"\bcoupons?\b", re.IGNORECASE),
    re.compile(r"\bdeals?\b", re.IGNORECASE),
    re.compile(r"\bpromo\s+codes?\b", re.IGNORECASE),
    re.compile(r"\bshopping\b", re.IGNORECASE),
)

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

WIRE_SOURCE_PATTERNS = (
    re.compile(r"\b(ap|associated press)\b", re.IGNORECASE),
    re.compile(r"\breuters\b", re.IGNORECASE),
)

LOW_TRUST_AGGREGATOR_PATTERNS = (
    re.compile(r"\bgoogle\s+news\b", re.IGNORECASE),
    re.compile(r"\bcnn\s+money\b", re.IGNORECASE),
    re.compile(r"\bmoney_latest\b", re.IGNORECASE),
)

GENERIC_ENTITY_TERMS = {
    "accounts",
    "america",
    "april",
    "ballroom",
    "best",
    "continue",
    "deadline",
    "details",
    "future",
    "latest",
    "news",
    "story",
    "today",
    "update",
    "updates",
}

KNOWN_PUBLIC_FIGURES = (
    "Ben Sasse",
    "Donald Trump",
    "Joe Biden",
    "Kamala Harris",
    "Nicolas Maduro",
    "Vladimir Putin",
    "Volodymyr Zelensky",
)

LOCATION_NAMES = (
    "Arizona",
    "Phoenix",
    "Tempe",
    "Scottsdale",
    "Mesa",
    "Tucson",
    "United States",
    "Washington",
    "White House",
)


@dataclass(frozen=True)
class SourceControls:
    priority: SourcePriority = "normal"
    allow_service_content: bool = False
    promote_to_home: bool = True
    category: str = ""


@dataclass(frozen=True)
class ContentQualityDecision:
    action: QualityAction
    reasons: tuple[str, ...]
    source_trust: SourceTrust
    source_controls: SourceControls
    content_class: ContentClass


@dataclass(frozen=True)
class ArticleClassification:
    content_class: ContentClass
    reasons: tuple[str, ...]
    primary_entities: tuple[str, ...]
    secondary_entities: tuple[str, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalized_url_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    candidate = normalize_whitespace(value)
    if not candidate:
        return ""
    try:
        return canonicalize_url(candidate).lower()
    except Exception:
        return candidate.lower()


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return default


def _priority_value(value: object, default: SourcePriority = "normal") -> SourcePriority:
    normalized = str(value or "").strip().lower()
    if normalized in {"high", "normal", "low"}:
        return normalized  # type: ignore[return-value]
    return default


def _controls_from_mapping(mapping: dict | None, default_category: str = "") -> SourceControls:
    if not isinstance(mapping, dict):
        return SourceControls(category=default_category)
    return SourceControls(
        priority=_priority_value(mapping.get("priority")),
        allow_service_content=_bool_value(mapping.get("allow_service_content"), False),
        promote_to_home=_bool_value(mapping.get("promote_to_home"), True),
        category=str(mapping.get("category") or default_category or "").strip(),
    )


@lru_cache(maxsize=1)
def _seed_controls_by_url() -> dict[str, SourceControls]:
    seed_path = _repo_root() / "data" / "miniflux_seed_feeds.json"
    if not seed_path.exists():
        return {}
    try:
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("feed_quality_seed_controls_unavailable path=%s error=%s", seed_path, exc)
        return {}

    controls: dict[str, SourceControls] = {}
    if not isinstance(raw, list):
        return controls

    for item in raw:
        if isinstance(item, str):
            url = item
            source_controls = SourceControls()
        elif isinstance(item, dict):
            url = str(item.get("url") or "")
            source_controls = _controls_from_mapping(item)
        else:
            continue
        key = _normalized_url_key(url)
        if key:
            controls[key] = source_controls
    return controls


def _feed_payload(raw_payload: dict) -> dict:
    feed = raw_payload.get("feed")
    return feed if isinstance(feed, dict) else {}


def _feed_url(raw_payload: dict) -> str:
    feed = _feed_payload(raw_payload)
    for key in ("feed_url", "url", "site_url"):
        value = feed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def source_controls_from_payload(raw_payload: dict) -> SourceControls:
    feed = _feed_payload(raw_payload)
    category = ""
    raw_category = feed.get("category")
    if isinstance(raw_category, dict):
        category = str(raw_category.get("title") or "").strip()
    elif isinstance(raw_category, str):
        category = raw_category.strip()

    direct_controls = _controls_from_mapping(feed, default_category=category)
    seed_controls = _seed_controls_by_url().get(_normalized_url_key(_feed_url(raw_payload)))
    if seed_controls is None:
        return direct_controls

    return SourceControls(
        priority=direct_controls.priority if direct_controls.priority != "normal" else seed_controls.priority,
        allow_service_content=direct_controls.allow_service_content or seed_controls.allow_service_content,
        promote_to_home=direct_controls.promote_to_home and seed_controls.promote_to_home,
        category=direct_controls.category or seed_controls.category,
    )


def _source_text(*, publisher: str, raw_payload: dict, controls: SourceControls) -> str:
    feed = _feed_payload(raw_payload)
    pieces = [
        publisher,
        str(feed.get("title") or ""),
        str(feed.get("feed_url") or ""),
        str(feed.get("url") or ""),
        str(feed.get("site_url") or ""),
        controls.category,
    ]
    return " ".join(piece for piece in pieces if piece)


def source_trust_for_payload(*, publisher: str, raw_payload: dict, controls: SourceControls | None = None) -> SourceTrust:
    source_controls = controls or source_controls_from_payload(raw_payload)
    source_text = _source_text(publisher=publisher, raw_payload=raw_payload, controls=source_controls)
    parsed_host = urlparse(_feed_url(raw_payload)).hostname or ""
    if parsed_host.lower().endswith("news.google.com") or any(pattern.search(source_text) for pattern in LOW_TRUST_AGGREGATOR_PATTERNS):
        return "low"
    if source_controls.priority == "low":
        return "low"
    if source_controls.priority == "high" or any(pattern.search(source_text) for pattern in WIRE_SOURCE_PATTERNS):
        return "high"
    return "normal"


def _quality_text(*, title: str, url: str, publisher: str, content_text: str, raw_payload: dict) -> str:
    feed = _feed_payload(raw_payload)
    pieces = [
        title,
        url,
        publisher,
        str(feed.get("title") or ""),
        str(feed.get("feed_url") or ""),
        str(feed.get("url") or ""),
        content_text[:1000],
    ]
    return " ".join(piece for piece in pieces if piece)


def _title_is_stale(title: str, *, now: datetime) -> bool:
    normalized = title.lower()
    current = now.astimezone(timezone.utc)

    for match in re.finditer(r"\b(20[0-9]{2})\b", normalized):
        year = int(match.group(1))
        if year < current.year:
            return True

    for month_name, month_number in MONTHS.items():
        month_with_year = re.search(rf"\b{month_name}\s+(20[0-9]{{2}})\b", normalized)
        if month_with_year:
            year = int(month_with_year.group(1))
            if year < current.year or (year == current.year and month_number < current.month):
                return True
            continue
        month_as_date = re.search(rf"\b(?:of|in)\s+{month_name}\b|\b{month_name}\s+\d{{1,2}}\b", normalized)
        if month_as_date and month_number < current.month:
            return True

    return False


def _ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    priority = [
        "stale_content",
        "affiliate_finance",
        "service_journalism",
        "low_trust_aggregator",
        "insufficient_high_quality_sources",
    ]
    return tuple(reason for reason in priority if reason in reasons)


def _is_generic_entity(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    if not normalized or normalized in GENERIC_ENTITY_TERMS:
        return True
    parts = normalized.split()
    return all(part in GENERIC_ENTITY_TERMS or len(part) <= 2 for part in parts)


def extract_robust_entities(text: str, *, publisher: str = "") -> tuple[tuple[str, ...], tuple[str, ...]]:
    candidates: list[str] = []
    source_candidates: list[str] = []
    for figure in KNOWN_PUBLIC_FIGURES:
        if re.search(rf"\b{re.escape(figure)}\b", text, re.IGNORECASE):
            candidates.append(figure)
    for location in LOCATION_NAMES:
        if re.search(rf"\b{re.escape(location)}\b", text, re.IGNORECASE):
            candidates.append(location)
    candidates.extend(re.findall(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3}\b", text))

    publisher_entity = re.sub(r"\s*[-|].*$", "", publisher or "").strip()
    if publisher_entity and len(publisher_entity.split()) <= 4:
        source_candidates.append(publisher_entity)

    seen: set[str] = set()
    entities: list[str] = []
    for candidate in candidates:
        entity = normalize_whitespace(candidate)
        if not entity or _is_generic_entity(entity):
            continue
        key = entity.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(entity)

    secondary = list(entities[6:14])
    for source_candidate in source_candidates:
        source_entity = normalize_whitespace(source_candidate)
        if source_entity and not _is_generic_entity(source_entity) and source_entity.lower() not in seen:
            secondary.append(source_entity)
            seen.add(source_entity.lower())
    return tuple(entities[:6]), tuple(secondary[:8])


def classify_article_content(
    *,
    title: str,
    url: str,
    publisher: str,
    content_text: str,
    raw_payload: dict,
    source_trust: SourceTrust | None = None,
) -> ArticleClassification:
    controls = source_controls_from_payload(raw_payload if isinstance(raw_payload, dict) else {})
    trust = source_trust or source_trust_for_payload(publisher=publisher, raw_payload=raw_payload, controls=controls)
    text = _quality_text(title=title, url=url, publisher=publisher, content_text=content_text, raw_payload=raw_payload)
    lowered = text.lower()

    primary_entities, secondary_entities = extract_robust_entities(
        f"{title} {content_text[:1000]}",
        publisher=publisher,
    )

    if trust == "low":
        return ArticleClassification("low_trust_aggregator", ("low_trust_aggregator",), primary_entities, secondary_entities)
    if any(pattern.search(text) for pattern in FINANCE_SERVICE_PATTERNS):
        return ArticleClassification("service_finance", ("affiliate_finance",), primary_entities, secondary_entities)
    if any(pattern.search(text) for pattern in SERVICE_JOURNALISM_PATTERNS):
        return ArticleClassification("evergreen", ("service_journalism",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("opinion", "editorial", "analysis", "commentary", "columns")):
        return ArticleClassification("opinion", ("commentary",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball")):
        return ArticleClassification("sports", ("sports",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("movie", "album", "celebrity", "box office", "streaming")):
        return ArticleClassification("entertainment", ("entertainment",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("agency.gov", ".gov/", "department of", "federal register", "press release")):
        return ArticleClassification("official_release", ("official_source",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("phoenix", "arizona", "tempe", "mesa", "scottsdale", "tucson")):
        return ArticleClassification("local_news", ("local_news",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("trump", "biden", "senate", "congress", "white house", "election", "governor")):
        return ArticleClassification("politics", ("politics",), primary_entities, secondary_entities)
    if any(token in lowered for token in ("stocks", "markets", "earnings", "fed ", "inflation", "tariff", "business")):
        return ArticleClassification("business_news", ("business_news",), primary_entities, secondary_entities)
    if primary_entities or any(token in lowered for token in ("killed", "shooting", "court", "charged", "war", "ceasefire")):
        return ArticleClassification("hard_news", ("hard_news",), primary_entities, secondary_entities)
    return ArticleClassification("unknown", ("unknown",), primary_entities, secondary_entities)


def evaluate_content_quality(
    *,
    title: str,
    url: str,
    publisher: str,
    published_at: datetime,
    content_text: str,
    raw_payload: dict,
    now: datetime | None = None,
) -> ContentQualityDecision:
    current = now or datetime.now(timezone.utc)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    controls = source_controls_from_payload(payload)
    source_trust = source_trust_for_payload(publisher=publisher, raw_payload=payload, controls=controls)
    classification = classify_article_content(
        title=title,
        url=url,
        publisher=publisher,
        content_text=content_text,
        raw_payload=payload,
        source_trust=source_trust,
    )
    text = _quality_text(title=title, url=url, publisher=publisher, content_text=content_text, raw_payload=payload)
    reasons: set[str] = set()

    if _title_is_stale(title, now=current):
        reasons.add("stale_content")
    if any(pattern.search(text) for pattern in FINANCE_SERVICE_PATTERNS):
        reasons.add("affiliate_finance")
    if any(pattern.search(text) for pattern in SERVICE_JOURNALISM_PATTERNS):
        reasons.add("service_journalism")
    if source_trust == "low":
        reasons.add("low_trust_aggregator")

    hard_reasons = reasons.intersection({"stale_content", "affiliate_finance", "service_journalism"})
    if controls.allow_service_content:
        hard_reasons = set()

    return ContentQualityDecision(
        action="reject" if hard_reasons else "accept",
        reasons=_ordered_reasons(reasons),
        source_trust=source_trust,
        source_controls=controls,
        content_class=classification.content_class,
    )


def evaluate_normalized_article_quality(
    normalized: NormalizedArticle,
    *,
    now: datetime | None = None,
) -> ContentQualityDecision:
    return evaluate_content_quality(
        title=normalized.title,
        url=normalized.url,
        publisher=normalized.publisher,
        published_at=normalized.published_at,
        content_text=normalized.content_text,
        raw_payload=normalized.raw_payload,
        now=now,
    )


def evaluate_article_quality(article: Article, *, now: datetime | None = None) -> ContentQualityDecision:
    raw_payload = article.raw_payload if isinstance(article.raw_payload, dict) else {}
    return evaluate_content_quality(
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        published_at=article.published_at,
        content_text=article.content_text,
        raw_payload=raw_payload,
        now=now,
    )
