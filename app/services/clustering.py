from __future__ import annotations

import json
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.services.content_quality import classify_article_content, evaluate_article_quality
from app.services.enrichment import (
    build_headline,
    build_key_facts,
    build_status,
    build_summary,
    build_timeline_events,
    build_what_changed,
    build_why_it_matters,
)
from app.services.normalizer import normalize_title
from app.services.topics import apply_topic_classification, classify_topic_from_article, derive_topic_from_article, derive_topic_from_articles, topic_matches
from app.services.validation import validate_cluster_record

logger = logging.getLogger(__name__)

CLUSTER_KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "blank",
    "but",
    "by",
    "com",
    "continue",
    "for",
    "from",
    "get",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "href",
    "https",
    "in",
    "into",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "our",
    "said",
    "says",
    "she",
    "that",
    "the",
    "their",
    "they",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "you",
    "your",
}

CLUSTER_GENERIC_NEWS_TERMS = {
    "attack",
    "attacks",
    "breaking",
    "ceasefire",
    "conflict",
    "crisis",
    "details",
    "developing",
    "latest",
    "live",
    "minister",
    "new",
    "reported",
    "reporting",
    "reports",
    "story",
    "update",
    "updates",
    "war",
}

LOCATION_TERMS = {
    "gaza",
    "iran",
    "israel",
    "lebanon",
    "mali",
    "sahel",
    "syria",
    "ukraine",
    "yemen",
}

ENTITY_OVERLAP_BLOCKLIST = {
    "accounts",
    "america",
    "april",
    "ballroom",
    "best",
    "continue",
    "deadline",
    "future",
    "latest",
    "transit",
}

ENTITY_ACRONYM_ALLOWLIST = {
    "ai",
    "cia",
    "eu",
    "fbi",
    "fda",
    "nasa",
    "nato",
    "opec",
    "uae",
    "uk",
    "un",
}

KEYWORD_ENTITY_ALLOWLIST = {
    "altman",
    "charles",
    "elon",
    "musk",
    "opec",
    "openai",
    "trump",
    "uae",
}

EVENT_TYPE_COMPATIBLE_FOLLOWUPS = {
    frozenset({"legal", "violence_conflict"}),
}


@dataclass(frozen=True)
class FeatureVector:
    title: str
    keywords: set[str]
    entities: set[str]
    primary_entities: set[str]
    key_entities: set[str]
    locations: set[str]
    title_tokens: set[str]
    title_entities: set[str]
    topic: str
    primary_topic: str
    subtopic: str | None
    geography: str | None
    event_type: str | None
    published_at: datetime
    publishers: set[str]
    content_class: str


@dataclass(frozen=True)
class CandidateEvaluation:
    cluster: Cluster
    title_similarity: float
    entity_jaccard: float
    keyword_jaccard: float
    semantic_score: float
    entity_overlap_score: float
    time_proximity: float
    entity_overlap: int
    key_entity_overlap: int
    keyword_overlap: int
    location_overlap: int
    title_token_overlap: int
    source_match: bool
    topic_match: bool
    primary_entity_overlap: bool
    title_primary_entity_overlap: bool
    near_duplicate_title: bool
    same_source_update_chain: bool
    primary_entity_conflict: bool
    conflicting_entities: tuple[str, ...]
    shared_entities: tuple[str, ...]
    subtopic_match: bool
    subtopic_conflict: bool
    geography_conflict: bool
    event_type_conflict: bool
    article_content_class: str
    cluster_content_class: str
    score: float
    signal_gate_passed: bool
    signal_reasons: tuple[str, ...]
    rejection_reason: str | None


@dataclass(frozen=True)
class RebuildResult:
    validation_failed: bool
    timeline_deduplicated: int
    promotion_attempted: bool
    promoted: bool
    promotion_failed: bool
    source_count: int
    status: str


@dataclass
class ClusteringRunResult:
    created_count: int
    updated_count: int
    candidates_evaluated: int
    signal_rejected: int
    attach_decisions: int
    new_decisions: int
    low_confidence_new: int
    validation_rejected: int
    timeline_deduplicated: int
    promoted_count: int
    hidden_total: int
    active_total: int
    promotion_attempts: int
    promotion_failures: int
    candidates_same_topic: int
    candidates_cross_topic_rejected: int
    entity_overlap_attaches: int
    entity_conflict_rejected: int
    no_candidate_new: int
    topic_lane_attaches: int
    topic_lane_new: int


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    intersection = len(left.intersection(right))
    union = len(left.union(right))
    if union == 0:
        return 0.0
    return intersection / union


def _title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _time_proximity(article_time: datetime, cluster_time: datetime, window_hours: int) -> float:
    delta_hours = abs((article_time - cluster_time).total_seconds()) / 3600
    if delta_hours >= window_hours:
        return 0.0
    return 1.0 - (delta_hours / max(window_hours, 1))


def _semantic_score(title_similarity: float, entity_jaccard: float, keyword_jaccard: float) -> float:
    return 0.50 * title_similarity + 0.30 * entity_jaccard + 0.20 * keyword_jaccard


def _content_class_mismatch(article_class: str, cluster_class: str) -> bool:
    if article_class == "unknown" or cluster_class == "unknown" or article_class == cluster_class:
        return False
    hard_news_classes = {"hard_news", "politics", "local_news", "business_news", "official_release"}
    service_classes = {"service_finance", "evergreen"}
    if article_class in service_classes and cluster_class in hard_news_classes:
        return True
    if cluster_class in service_classes and article_class in hard_news_classes:
        return True
    if article_class == "opinion" and cluster_class in {"hard_news", "politics", "local_news"}:
        return True
    if cluster_class == "opinion" and article_class in {"hard_news", "politics", "local_news"}:
        return True
    if article_class in {"sports", "entertainment"} and cluster_class in hard_news_classes:
        return True
    if cluster_class in {"sports", "entertainment"} and article_class in hard_news_classes:
        return True
    return False


def _membership_rejection_status(
    candidate_rejection_reason: str | None,
    source_quality_reasons: tuple[str, ...],
    article_content_class: str,
    *,
    decision: str,
) -> str | None:
    if decision == "attach_existing_cluster":
        return None
    if article_content_class == "service_finance" or "affiliate_finance" in source_quality_reasons:
        return "rejected_service_finance"
    if "stale_content" in source_quality_reasons:
        return "rejected_stale_article"
    if article_content_class == "low_trust_aggregator":
        return "low_trust_aggregator_only"
    if candidate_rejection_reason == "content_class_mismatch":
        return "rejected_content_class_mismatch"
    if candidate_rejection_reason in {
        "missing_primary_entity_overlap",
        "distinct_primary_entities",
        "location_conflict_without_entity_overlap",
        "distinct_event_signatures",
        "event_type_conflict",
        "geography_conflict",
        "generic_keyword_only_overlap",
        "weak_primary_entity_context",
    }:
        return "rejected_low_entity_overlap"
    if candidate_rejection_reason == "low_trust_aggregator_attach_blocked":
        return "low_trust_aggregator_only"
    if candidate_rejection_reason in {
        "primary_topic_mismatch",
        "subtopic_mismatch_without_strong_entity_overlap",
        "weak_semantic_signals",
        "topic_mismatch",
        "story_window_expired",
    }:
        return "rejected_low_similarity"
    return "candidate_needs_more_sources"


def _tokenize_text(value: str) -> set[str]:
    return {token.strip().lower() for token in (value or "").replace("/", " ").replace("-", " ").split() if token.strip()}


def _semantic_keywords(values: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    keywords: set[str] = set()
    for value in values or []:
        keyword = str(value).strip().lower()
        if keyword and keyword not in CLUSTER_KEYWORD_STOPWORDS and keyword not in CLUSTER_GENERIC_NEWS_TERMS:
            keywords.add(keyword)
    return keywords


def _semantic_entities(values: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    entities: set[str] = set()
    for value in values or []:
        entity = str(value).strip().lower()
        if (
            not entity
            or entity in ENTITY_OVERLAP_BLOCKLIST
            or entity in CLUSTER_KEYWORD_STOPWORDS
            or entity in CLUSTER_GENERIC_NEWS_TERMS
        ):
            continue
        parts = {part for part in _tokenize_text(entity) if part}
        if parts and parts.issubset(ENTITY_OVERLAP_BLOCKLIST | CLUSTER_KEYWORD_STOPWORDS | CLUSTER_GENERIC_NEWS_TERMS):
            continue
        entities.add(entity)
    return entities


def _keyword_entities(keywords: set[str], title: str) -> set[str]:
    title_tokens = _tokenize_text(title)
    return {
        keyword
        for keyword in keywords
        if keyword in KEYWORD_ENTITY_ALLOWLIST and (keyword in title_tokens or keyword in ENTITY_ACRONYM_ALLOWLIST)
    }


def _entity_aliases(entities: set[str]) -> set[str]:
    aliases = set(entities)
    for entity in entities:
        tokens = [
            token
            for token in _tokenize_text(entity)
            if len(token) > 3
            and token not in ENTITY_OVERLAP_BLOCKLIST
            and token not in CLUSTER_KEYWORD_STOPWORDS
            and token not in CLUSTER_GENERIC_NEWS_TERMS
        ]
        if len(tokens) >= 2:
            aliases.update(tokens)
    return aliases


def _primary_entities_from_values(
    values: list[str] | set[str] | tuple[str, ...] | None,
    classification_entities: tuple[str, ...] = (),
) -> set[str]:
    primary = _semantic_entities(classification_entities)
    for entity in _semantic_entities(values):
        if " " in entity or entity in LOCATION_TERMS or entity in ENTITY_ACRONYM_ALLOWLIST:
            primary.add(entity)
    return _entity_aliases(primary)


def _semantic_locations(*, title: str, keywords: set[str], entities: set[str]) -> set[str]:
    title_tokens = _tokenize_text(title)
    candidates = title_tokens.union(keywords).union(_tokenize_text(" ".join(entities)))
    return {token for token in candidates if token in LOCATION_TERMS}


def _entity_overlap_score(overlap_count: int, key_overlap_count: int, location_overlap: int) -> float:
    if overlap_count <= 0 and key_overlap_count <= 0 and location_overlap <= 0:
        return 0.0
    return min(1.0, 0.35 * overlap_count + 0.35 * key_overlap_count + 0.20 * location_overlap)


def _clean_lane_value(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower().replace(" ", "_")
    return cleaned or None


def _geography_bucket(value: str | None) -> str | None:
    cleaned = _clean_lane_value(value)
    if cleaned in {
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new_hampshire",
        "new_jersey",
        "new_mexico",
        "new_york",
        "north_carolina",
        "north_dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode_island",
        "south_carolina",
        "south_dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west_virginia",
        "wisconsin",
        "wyoming",
    }:
        return "united_states"
    return cleaned


def _geography_conflicts(left: str | None, right: str | None) -> bool:
    left_clean = _clean_lane_value(left)
    right_clean = _clean_lane_value(right)
    if not left_clean or not right_clean or left_clean == right_clean:
        return False
    return _geography_bucket(left_clean) != _geography_bucket(right_clean)


def _event_type_conflicts(left: str | None, right: str | None) -> bool:
    left_clean = _clean_lane_value(left)
    right_clean = _clean_lane_value(right)
    return bool(left_clean and right_clean and left_clean != right_clean)


def _event_type_compatible_followup(left: str | None, right: str | None) -> bool:
    left_clean = _clean_lane_value(left)
    right_clean = _clean_lane_value(right)
    if not left_clean or not right_clean or left_clean == right_clean:
        return True
    return frozenset({left_clean, right_clean}) in EVENT_TYPE_COMPATIBLE_FOLLOWUPS


def _title_signature_tokens(title: str) -> set[str]:
    return {
        token
        for token in _tokenize_text(title)
        if len(token) > 3 and token not in CLUSTER_KEYWORD_STOPWORDS and token not in CLUSTER_GENERIC_NEWS_TERMS
    }


def _normalized_phrase(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value or "")
    return " ".join(cleaned.split())


def _entities_mentioned_in_title(entities: set[str], title: str) -> set[str]:
    normalized_title_text = _normalized_phrase(title)
    normalized_title = f" {normalized_title_text} "
    title_tokens = _tokenize_text(normalized_title_text)
    mentioned: set[str] = set()
    for entity in entities:
        entity_key = _normalized_phrase(entity)
        if entity_key and f" {entity_key} " in normalized_title:
            mentioned.add(entity)
            continue

        entity_tokens = {
            token
            for token in _tokenize_text(entity_key)
            if len(token) > 3 and token not in CLUSTER_KEYWORD_STOPWORDS and token not in CLUSTER_GENERIC_NEWS_TERMS
        }
        if entity_tokens and title_tokens.intersection(entity_tokens):
            mentioned.add(entity)
    return mentioned


def _article_features(article: Article) -> FeatureVector:
    keywords = _semantic_keywords(article.keywords)
    topic_classification = apply_topic_classification(article)
    base_entities = _semantic_entities(article.entities)
    title = article.title or article.normalized_title
    key_entities = _semantic_entities(article.key_entities) if base_entities else set()
    key_entities.update(_keyword_entities(keywords, title))
    entities = _entity_aliases(base_entities)
    entities.update(_entity_aliases(key_entities))
    raw_payload = article.raw_payload if isinstance(article.raw_payload, dict) else {}
    quality = evaluate_article_quality(article)
    classification = classify_article_content(
        title=article.title,
        url=article.url,
        publisher=article.publisher,
        content_text=article.content_text,
        raw_payload=raw_payload,
        source_trust=quality.source_trust,
    )
    if base_entities:
        entities.update(_entity_aliases(_semantic_entities(classification.primary_entities)))
    primary_entities = _primary_entities_from_values(
        [*base_entities, *key_entities],
        classification.primary_entities if base_entities else (),
    )
    return FeatureVector(
        title=article.normalized_title,
        keywords=keywords,
        entities=entities,
        primary_entities=primary_entities,
        key_entities=key_entities,
        locations=_semantic_locations(title=title, keywords=keywords, entities=entities),
        title_tokens=_title_signature_tokens(article.normalized_title),
        title_entities=_entities_mentioned_in_title(primary_entities, title),
        topic=derive_topic_from_article(article),
        primary_topic=topic_classification.primary_topic,
        subtopic=topic_classification.subtopic,
        geography=topic_classification.geography,
        event_type=topic_classification.event_type,
        published_at=article.published_at,
        publishers={(article.publisher or "").strip().lower()} if (article.publisher or "").strip() else set(),
        content_class=classification.content_class,
    )


def _cluster_features(cluster: Cluster) -> FeatureVector:
    cluster_topic = cluster.topic or derive_topic_from_articles(list(cluster.source_links))
    keywords = _semantic_keywords(cluster.keywords)
    base_entities = _semantic_entities(cluster.entities)
    key_entities = _semantic_entities(cluster.key_entities) if base_entities else set()
    key_entities.update(_keyword_entities(keywords, cluster.headline or cluster.normalized_headline))
    entities = _entity_aliases(base_entities)
    entities.update(_entity_aliases(key_entities))
    primary_entities = _primary_entities_from_values([*base_entities, *key_entities])
    primary_topic = (cluster.primary_topic or "").strip()
    subtopic = cluster.subtopic
    geography = cluster.geography
    event_type = cluster.event_type
    publishers = {
        (link.article.publisher or "").strip().lower()
        for link in cluster.source_links
        if link.article is not None and (link.article.publisher or "").strip()
    }
    class_counts: dict[str, int] = {}
    for link in cluster.source_links:
        if link.article is None:
            continue
        article_quality = evaluate_article_quality(link.article)
        raw_payload = link.article.raw_payload if isinstance(link.article.raw_payload, dict) else {}
        classification = classify_article_content(
            title=link.article.title,
            url=link.article.url,
            publisher=link.article.publisher,
            content_text=link.article.content_text,
            raw_payload=raw_payload,
            source_trust=article_quality.source_trust,
        )
        article_class = classification.content_class
        class_counts[article_class] = class_counts.get(article_class, 0) + 1
        topic_classification = classify_topic_from_article(link.article)
        primary_topic = primary_topic or topic_classification.primary_topic
        if subtopic is None:
            subtopic = topic_classification.subtopic
        if geography is None:
            geography = topic_classification.geography
        if event_type is None:
            event_type = topic_classification.event_type
        article_base_entities = _semantic_entities(link.article.entities)
        article_key_entities = _semantic_entities(link.article.key_entities) if article_base_entities else set()
        article_keywords = _semantic_keywords(link.article.keywords)
        article_title = link.article.title or link.article.normalized_title
        article_key_entities.update(_keyword_entities(article_keywords, article_title))
        primary_entities.update(
            _primary_entities_from_values(
                [*article_base_entities, *article_key_entities],
                classification.primary_entities if article_base_entities else (),
            )
        )
        entities.update(_entity_aliases(article_base_entities))
        entities.update(_entity_aliases(article_key_entities))
    content_class = max(class_counts.items(), key=lambda item: (item[1], item[0]))[0] if class_counts else "unknown"
    return FeatureVector(
        title=cluster.normalized_headline,
        keywords=keywords,
        entities=entities,
        primary_entities=primary_entities,
        key_entities=key_entities,
        locations=_semantic_locations(title=cluster.headline or cluster.normalized_headline, keywords=keywords, entities=entities),
        title_tokens=_title_signature_tokens(cluster.normalized_headline),
        title_entities=_entities_mentioned_in_title(primary_entities, cluster.headline or cluster.normalized_headline),
        topic=cluster_topic,
        primary_topic=primary_topic or "U.S.",
        subtopic=subtopic,
        geography=geography,
        event_type=event_type,
        published_at=cluster.last_updated,
        publishers=publishers,
        content_class=content_class,
    )


def _evaluate_candidate(
    cluster: Cluster,
    article: FeatureVector,
    cluster_features: FeatureVector,
    settings: Settings,
) -> CandidateEvaluation:
    title_similarity = _title_similarity(article.title, cluster_features.title)
    entity_jaccard = _jaccard(article.entities, cluster_features.entities)
    keyword_jaccard = _jaccard(article.keywords, cluster_features.keywords)
    semantic_score = _semantic_score(title_similarity, entity_jaccard, keyword_jaccard)
    time_proximity = _time_proximity(article.published_at, cluster_features.published_at, settings.cluster_time_window_hours)
    topic_match = topic_matches(article.topic, cluster_features.topic)
    raw_class_mismatch = _content_class_mismatch(article.content_class, cluster_features.content_class)
    primary_topic_match = article.primary_topic == cluster_features.primary_topic
    subtopic_match = not article.subtopic or not cluster_features.subtopic or article.subtopic == cluster_features.subtopic

    entity_overlap = len(article.entities.intersection(cluster_features.entities))
    key_entity_overlap = len(article.key_entities.intersection(cluster_features.key_entities))
    keyword_overlap = len(article.keywords.intersection(cluster_features.keywords))
    location_overlap = len(article.locations.intersection(cluster_features.locations))
    source_match = bool(article.publishers.intersection(cluster_features.publishers))
    shared_primary_entities = article.primary_entities.intersection(cluster_features.primary_entities)
    shared_entities = article.entities.intersection(cluster_features.entities)
    primary_entity_overlap = bool(shared_primary_entities)
    conflicting_entities: set[str] = set()
    if article.primary_entities and cluster_features.primary_entities and not shared_primary_entities:
        conflicting_entities = article.primary_entities.symmetric_difference(cluster_features.primary_entities)
    near_duplicate_title = title_similarity >= settings.cluster_min_title_signal
    shared_title_tokens = article.title_tokens.intersection(cluster_features.title_tokens)
    title_token_overlap = len(shared_title_tokens)
    generic_only_keyword_overlap = keyword_overlap > 0 and not (
        article.keywords.intersection(cluster_features.keywords) - CLUSTER_GENERIC_NEWS_TERMS
    )
    title_primary_entity_overlap = bool(article.title_entities.intersection(cluster_features.title_entities))
    strong_story_identity = bool(
        primary_entity_overlap
        and title_primary_entity_overlap
        and (keyword_overlap >= settings.cluster_min_keyword_overlap or title_token_overlap >= 2)
    )
    title_entity_conflict = bool(article.title_entities and cluster_features.title_entities and not title_primary_entity_overlap)
    strong_named_entity_conflict = bool(
        article.primary_entities
        and cluster_features.primary_entities
        and not shared_primary_entities
        and title_entity_conflict
        and title_token_overlap < 2
        and keyword_overlap < settings.cluster_min_keyword_overlap
    )
    primary_entity_conflict = bool(not shared_primary_entities and (title_entity_conflict or strong_named_entity_conflict))
    strong_entity_overlap = primary_entity_overlap and entity_overlap >= max(2, settings.cluster_min_entity_overlap + 1)
    subtopic_conflict = bool(not subtopic_match and not strong_entity_overlap)
    geography_conflict = bool(_geography_conflicts(article.geography, cluster_features.geography) and not strong_story_identity)
    class_mismatch = bool(raw_class_mismatch and not strong_story_identity)
    raw_event_type_conflict = _event_type_conflicts(article.event_type, cluster_features.event_type)
    event_type_conflict = bool(
        raw_event_type_conflict
        and not (
            primary_topic_match
            and subtopic_match
            and _event_type_compatible_followup(article.event_type, cluster_features.event_type)
            and (entity_overlap > 0 or title_token_overlap >= 2)
        )
    )

    entity_overlap_score = _entity_overlap_score(entity_overlap, key_entity_overlap, location_overlap)
    score = round(
        0.40 * title_similarity
        + 0.20 * entity_jaccard
        + 0.15 * keyword_jaccard
        + 0.15 * entity_overlap_score
        + 0.10 * time_proximity,
        4,
    )

    signal_reasons: list[str] = []
    if title_similarity >= settings.cluster_min_title_signal:
        signal_reasons.append("strong_title_similarity")
    if entity_overlap >= settings.cluster_min_entity_overlap:
        signal_reasons.append("meaningful_entity_overlap")
    if keyword_overlap >= settings.cluster_min_keyword_overlap:
        signal_reasons.append("meaningful_keyword_overlap")
    if location_overlap > 0:
        signal_reasons.append("location_overlap")
    if topic_match and semantic_score >= settings.cluster_min_topic_semantic_score:
        signal_reasons.append("topic_semantic_similarity")
    if (
        topic_match
        and title_similarity >= settings.cluster_attach_override_min_title_similarity
        and keyword_overlap > 0
    ):
        signal_reasons.append("topic_title_keyword_similarity")

    semantic_backstop = (
        entity_overlap >= max(2, settings.cluster_min_entity_overlap + 1)
        or (entity_overlap >= settings.cluster_min_entity_overlap and location_overlap > 0)
    ) and title_similarity >= settings.cluster_attach_override_min_title_similarity
    primary_entity_continuity = (
        primary_entity_overlap
        and title_primary_entity_overlap
        and time_proximity >= settings.cluster_attach_override_min_time_proximity
        and (
            near_duplicate_title
            or keyword_overlap >= settings.cluster_min_keyword_overlap
            or semantic_score >= settings.cluster_min_topic_semantic_score
        )
    )
    same_source_evidence = (
        near_duplicate_title
        or (
            title_token_overlap >= 2
            and keyword_overlap >= settings.cluster_min_keyword_overlap + 1
            and semantic_score >= settings.cluster_min_topic_semantic_score
        )
    )
    same_source_update_chain = (
        source_match
        and topic_match
        and time_proximity >= settings.cluster_attach_override_min_time_proximity
        and same_source_evidence
    )
    topic_keyword_title_continuity = (
        topic_match
        and title_token_overlap >= 2
        and keyword_overlap >= settings.cluster_min_keyword_overlap + 1
        and semantic_score >= settings.cluster_min_topic_semantic_score
    )
    same_event_lane_continuity = (
        primary_topic_match
        and subtopic_match
        and not geography_conflict
        and not event_type_conflict
        and not primary_entity_conflict
        and title_primary_entity_overlap
        and title_token_overlap >= 2
        and keyword_overlap >= settings.cluster_min_keyword_overlap
        and semantic_score >= settings.cluster_attach_override_min_title_similarity
        and _event_type_compatible_followup(article.event_type, cluster_features.event_type)
    )
    topic_lane_entity_continuity = (
        primary_topic_match
        and subtopic_match
        and not geography_conflict
        and not event_type_conflict
        and not primary_entity_conflict
        and primary_entity_overlap
        and title_primary_entity_overlap
        and entity_overlap >= settings.cluster_min_entity_overlap
        and (keyword_overlap > 0 or title_token_overlap > 0)
        and semantic_score >= 0.18
    )
    topic_followup_continuity = (
        primary_entity_overlap
        and title_primary_entity_overlap
        and topic_match
        and time_proximity >= settings.cluster_attach_override_min_time_proximity
        and title_similarity >= settings.cluster_attach_override_min_title_similarity
        and keyword_overlap > 0
        and entity_overlap >= max(2, settings.cluster_min_entity_overlap + 1)
    )
    if primary_entity_continuity:
        signal_reasons.append("primary_entity_continuity")
    if same_source_update_chain:
        signal_reasons.append("same_source_update_chain")
    if topic_keyword_title_continuity:
        signal_reasons.append("topic_keyword_title_continuity")
    if same_event_lane_continuity:
        signal_reasons.append("same_event_lane_continuity")
    if topic_lane_entity_continuity:
        signal_reasons.append("topic_lane_entity_continuity")
    if topic_followup_continuity:
        signal_reasons.append("topic_followup_continuity")
    if near_duplicate_title:
        signal_reasons.append("near_duplicate_title")
    signal_gate_passed = bool(signal_reasons) and (
        topic_match
        or semantic_backstop
        or primary_entity_continuity
        or same_source_update_chain
        or same_event_lane_continuity
        or topic_lane_entity_continuity
    )
    if not primary_topic_match:
        signal_gate_passed = False
        rejection_reason = "primary_topic_mismatch"
    elif subtopic_conflict:
        signal_gate_passed = False
        rejection_reason = "subtopic_mismatch_without_strong_entity_overlap"
    elif geography_conflict:
        signal_gate_passed = False
        rejection_reason = "geography_conflict"
    elif event_type_conflict:
        signal_gate_passed = False
        rejection_reason = "event_type_conflict"
    elif class_mismatch:
        signal_gate_passed = False
        rejection_reason = "content_class_mismatch"
    elif article.content_class == "low_trust_aggregator" and not (
        near_duplicate_title and title_primary_entity_overlap and semantic_score >= settings.cluster_min_topic_semantic_score
    ):
        signal_gate_passed = False
        rejection_reason = "low_trust_aggregator_attach_blocked"
    elif time_proximity <= 0 and not near_duplicate_title:
        signal_gate_passed = False
        rejection_reason = "story_window_expired"
    elif primary_entity_conflict:
        signal_gate_passed = False
        rejection_reason = "distinct_primary_entities"
    elif (
        primary_entity_overlap
        and not title_primary_entity_overlap
        and not near_duplicate_title
        and not same_source_update_chain
        and not topic_keyword_title_continuity
        and not topic_followup_continuity
        and not same_event_lane_continuity
        and not topic_lane_entity_continuity
    ):
        signal_gate_passed = False
        rejection_reason = "weak_primary_entity_context"
    elif (
        signal_gate_passed
        and not primary_entity_overlap
        and not near_duplicate_title
        and not same_source_update_chain
        and not same_event_lane_continuity
    ):
        signal_gate_passed = False
        rejection_reason = "missing_primary_entity_overlap"
    elif article.locations and cluster_features.locations and location_overlap == 0 and entity_overlap == 0:
        signal_gate_passed = False
        rejection_reason = "location_conflict_without_entity_overlap"
    elif len(article.title_tokens) >= 2 and len(cluster_features.title_tokens) >= 2 and not shared_title_tokens and entity_overlap == 0:
        signal_gate_passed = False
        rejection_reason = "distinct_event_signatures"
    elif generic_only_keyword_overlap and entity_overlap == 0 and title_similarity < settings.cluster_min_title_signal:
        signal_gate_passed = False
        rejection_reason = "generic_keyword_only_overlap"
    elif not topic_match and not semantic_backstop and not primary_entity_continuity and not topic_lane_entity_continuity:
        rejection_reason = "topic_mismatch"
    elif not signal_reasons:
        rejection_reason = "weak_semantic_signals"
    else:
        rejection_reason = None

    return CandidateEvaluation(
        cluster=cluster,
        title_similarity=round(title_similarity, 4),
        entity_jaccard=round(entity_jaccard, 4),
        keyword_jaccard=round(keyword_jaccard, 4),
        semantic_score=round(semantic_score, 4),
        entity_overlap_score=round(entity_overlap_score, 4),
        time_proximity=round(time_proximity, 4),
        entity_overlap=entity_overlap,
        key_entity_overlap=key_entity_overlap,
        keyword_overlap=keyword_overlap,
        location_overlap=location_overlap,
        title_token_overlap=title_token_overlap,
        source_match=source_match,
        topic_match=topic_match,
        primary_entity_overlap=primary_entity_overlap,
        title_primary_entity_overlap=title_primary_entity_overlap,
        near_duplicate_title=near_duplicate_title,
        same_source_update_chain=same_source_update_chain,
        primary_entity_conflict=primary_entity_conflict,
        conflicting_entities=tuple(sorted(conflicting_entities)),
        shared_entities=tuple(sorted(shared_entities)),
        subtopic_match=subtopic_match,
        subtopic_conflict=subtopic_conflict,
        geography_conflict=geography_conflict,
        event_type_conflict=event_type_conflict,
        article_content_class=article.content_class,
        cluster_content_class=cluster_features.content_class,
        score=score,
        signal_gate_passed=signal_gate_passed,
        signal_reasons=tuple(signal_reasons),
        rejection_reason=rejection_reason,
    )


def _is_better_candidate(candidate: CandidateEvaluation, incumbent: CandidateEvaluation | None, epsilon: float) -> bool:
    if incumbent is None:
        return True

    if candidate.score > incumbent.score + epsilon:
        return True
    if incumbent.score > candidate.score + epsilon:
        return False

    candidate_rank = (candidate.entity_overlap, candidate.keyword_overlap, candidate.cluster.last_updated, candidate.cluster.id)
    incumbent_rank = (incumbent.entity_overlap, incumbent.keyword_overlap, incumbent.cluster.last_updated, incumbent.cluster.id)
    return candidate_rank > incumbent_rank


def _candidate_has_strong_cross_subtopic_overlap(article: FeatureVector, cluster: Cluster, settings: Settings) -> bool:
    cluster_entities = _entity_aliases(_semantic_entities(cluster.entities))
    cluster_key_entities = _semantic_entities(cluster.key_entities) if cluster_entities else set()
    shared_entities = article.entities.intersection(cluster_entities)
    shared_key_entities = article.key_entities.intersection(cluster_key_entities)
    if shared_key_entities:
        return True
    if len(shared_entities) >= max(2, settings.cluster_min_entity_overlap + 1):
        return True
    return bool(shared_key_entities and len(shared_entities) >= settings.cluster_min_entity_overlap)


def _load_unclustered_articles(session: Session, limit: int, article_ids: list[int] | None = None) -> list[Article]:
    stmt: Select[tuple[Article]] = (
        select(Article)
        .outerjoin(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.id.is_(None))
        .order_by(Article.published_at.asc(), Article.id.asc())
        .limit(limit)
    )
    if article_ids is not None:
        if not article_ids:
            return []
        stmt = stmt.where(Article.id.in_(article_ids))
    return list(session.scalars(stmt).all())


def _load_candidate_clusters(session: Session, article: Article, article_features: FeatureVector, settings: Settings) -> list[Cluster]:
    threshold_time = article.published_at - timedelta(hours=settings.cluster_time_window_hours)
    primary_topic = (article.primary_topic or "").strip() or article_features.primary_topic
    subtopic = (article.subtopic or article_features.subtopic or "").strip()
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .where(Cluster.last_updated >= threshold_time, Cluster.primary_topic == primary_topic)
        .order_by(Cluster.last_updated.desc())
    )
    if subtopic:
        stmt = stmt.where(Cluster.subtopic == subtopic)
        same_lane = list(session.scalars(stmt).all())
        cross_stmt: Select[tuple[Cluster]] = (
            select(Cluster)
            .where(
                Cluster.last_updated >= threshold_time,
                Cluster.primary_topic == primary_topic,
                or_(Cluster.subtopic.is_(None), Cluster.subtopic != subtopic),
            )
            .order_by(Cluster.last_updated.desc())
        )
        cross_lane = [
            cluster
            for cluster in session.scalars(cross_stmt).all()
            if _candidate_has_strong_cross_subtopic_overlap(article_features, cluster, settings)
        ]
        return same_lane + cross_lane
    null_lane = list(session.scalars(stmt.where(Cluster.subtopic.is_(None))).all())
    subtopic_lane_stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .where(
            Cluster.last_updated >= threshold_time,
            Cluster.primary_topic == primary_topic,
            Cluster.subtopic.is_not(None),
        )
        .order_by(Cluster.last_updated.desc())
    )
    strong_subtopic_lane = [
        cluster
        for cluster in session.scalars(subtopic_lane_stmt).all()
        if _candidate_has_strong_cross_subtopic_overlap(article_features, cluster, settings)
    ]
    return null_lane + strong_subtopic_lane


def _is_legacy_source_count_validation_error(validation_error: str | None, settings: Settings) -> bool:
    if not validation_error:
        return False
    legacy_message = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    return validation_error == legacy_message


def _load_repromotable_hidden_clusters(session: Session, settings: Settings) -> list[Cluster]:
    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .where(
            Cluster.status == "hidden",
            source_count_subquery >= settings.cluster_min_sources_for_api,
            (Cluster.validation_error.is_(None) | (Cluster.validation_error == legacy_source_count_error)),
        )
        .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
    )
    return list(session.scalars(stmt).all())


def _promotion_blockers(
    *,
    source_count: int,
    validation_error: str | None,
    settings: Settings,
    articles: list[Article] | None = None,
) -> list[str]:
    blockers: list[str] = []

    if source_count < settings.cluster_min_sources_for_api:
        blockers.append(
            f"source_count_below_threshold: needs at least {settings.cluster_min_sources_for_api} sources, has {source_count}"
        )

    if validation_error and not _is_legacy_source_count_validation_error(validation_error, settings):
        blockers.append(f"validation_failed: {validation_error}")

    if articles:
        distinct_publishers = {
            (article.publisher or "").strip().lower()
            for article in articles
            if (article.publisher or "").strip()
        }
        required_distinct_sources = min(settings.cluster_min_distinct_sources_for_api, settings.cluster_min_sources_for_api)
        if len(distinct_publishers) < required_distinct_sources:
            blockers.append(
                "source_diversity_below_threshold: "
                f"needs at least {required_distinct_sources} distinct sources, has {len(distinct_publishers)}"
            )

        quality_decisions = [evaluate_article_quality(article) for article in articles]
        classifications = [
            classify_article_content(
                title=article.title,
                url=article.url,
                publisher=article.publisher,
                content_text=article.content_text,
                raw_payload=article.raw_payload if isinstance(article.raw_payload, dict) else {},
                source_trust=quality.source_trust,
            )
            for article, quality in zip(articles, quality_decisions, strict=False)
        ]
        blocking_reasons = {
            reason
            for decision in quality_decisions
            for reason in decision.reasons
            if reason in {"stale_content", "affiliate_finance", "service_journalism"}
        }
        if any(item.content_class == "service_finance" for item in classifications):
            blocking_reasons.add("affiliate_finance")
        if any(item.content_class == "evergreen" for item in classifications):
            blocking_reasons.add("service_journalism")
        for reason in sorted(blocking_reasons):
            blockers.append(f"{reason}: source article failed ingestion quality policy")

        has_home_eligible_source = any(
            decision.action == "accept"
            and decision.source_trust in {"high", "normal"}
            and decision.source_controls.promote_to_home
            for decision in quality_decisions
        )
        if not has_home_eligible_source:
            blockers.append(
                "insufficient_high_quality_sources: needs at least one normal/high trust source eligible for homepage promotion"
            )

    return blockers


def _most_common(values: list[str | None]) -> str | None:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, value in enumerate(values):
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        counts[cleaned] = counts.get(cleaned, 0) + 1
        first_seen.setdefault(cleaned, index)
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda item: (-item[1], first_seen[item[0]], item[0]))
    return ranked[0][0]


def _cluster_lane_metadata(articles: list[Article]) -> tuple[str, str | None, list[str], str | None, str | None]:
    classifications = [apply_topic_classification(article) for article in articles]
    primary_topic = _most_common([item.primary_topic for item in classifications]) or "U.S."
    subtopic = _most_common([item.subtopic for item in classifications if item.primary_topic == primary_topic])
    geography = _most_common([item.geography for item in classifications])
    event_type = _most_common([item.event_type for item in classifications])
    key_entities: list[str] = []
    seen: set[str] = set()
    for classification in classifications:
        for entity in classification.key_entities:
            key = entity.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            key_entities.append(entity)
            if len(key_entities) >= 12:
                break
        if len(key_entities) >= 12:
            break
    return primary_topic, subtopic, key_entities, geography, event_type


def _source_count_subquery():
    return (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )


def _normalized_topic(value: str | None) -> str:
    return (value or "").strip().lower()


def _has_related_topic(left: Cluster, right: Cluster) -> bool:
    left_topic = _normalized_topic(left.topic)
    right_topic = _normalized_topic(right.topic)
    if not left_topic or not right_topic or left_topic == "general" or right_topic == "general":
        return False
    return topic_matches(left.topic, right.topic)


def _related_score(left: Cluster, right: Cluster, settings: Settings) -> tuple[int, int, int, datetime, str] | None:
    left_entities = _semantic_entities(left.entities)
    right_entities = _semantic_entities(right.entities)
    left_keywords = _semantic_keywords(left.keywords)
    right_keywords = _semantic_keywords(right.keywords)
    entity_overlap = len(left_entities.intersection(right_entities))
    keyword_overlap = len(left_keywords.intersection(right_keywords))
    topic_match = _has_related_topic(left, right)

    if not topic_match and entity_overlap == 0 and keyword_overlap < settings.cluster_min_keyword_overlap:
        return None

    score = int(topic_match) * 4 + entity_overlap * 3 + keyword_overlap
    return (score, entity_overlap, keyword_overlap, right.last_updated, right.id)


def _refresh_related_clusters(session: Session, settings: Settings) -> None:
    source_count = _source_count_subquery()
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    clusters = list(
        session.scalars(
            select(Cluster)
            .where(
                Cluster.status != "hidden",
                source_count >= settings.cluster_min_sources_for_api,
                (Cluster.validation_error.is_(None) | (Cluster.validation_error == legacy_source_count_error)),
            )
            .order_by(Cluster.last_updated.desc(), Cluster.id.asc())
        ).all()
    )

    for cluster in clusters:
        ranked: list[tuple[tuple[int, int, int, datetime, str], str]] = []
        for candidate in clusters:
            if candidate.id == cluster.id:
                continue
            score = _related_score(cluster, candidate, settings)
            if score is None:
                continue
            ranked.append((score, candidate.id))

        ranked.sort(reverse=True)
        cluster.related_cluster_ids = [cluster_id for _, cluster_id in ranked[:4]]


def _build_heuristic_breakdown(
    *,
    decision: str,
    decision_reason: str,
    candidate_count: int,
    settings: Settings,
    evaluation: CandidateEvaluation | None,
    attach_override_met: bool = False,
    attach_override_components: dict[str, float | int | bool] | None = None,
    source_quality_reasons: tuple[str, ...] = (),
    source_trust: str = "normal",
    candidate_diagnostics: list[dict] | None = None,
) -> dict:
    if evaluation is None:
        components = {
            "title_similarity": 0.0,
            "entity_jaccard": 0.0,
            "keyword_jaccard": 0.0,
            "semantic_score": 0.0,
            "entity_overlap_score": 0.0,
            "time_proximity": 0.0,
        }
        overlap_counts = {
            "entity_overlap": 0,
            "key_entity_overlap": 0,
            "keyword_overlap": 0,
            "location_overlap": 0,
            "title_token_overlap": 0,
        }
        selected_score = 0.0
        selected_cluster_id = None
        signal_gate_passed = False
        signal_reasons: tuple[str, ...] = ()
        candidate_rejection_reason = None
        article_content_class = "unknown"
        cluster_content_class = "unknown"
        primary_entity_overlap = False
        title_primary_entity_overlap = False
        near_duplicate_title = False
        same_source_update_chain = False
        primary_entity_conflict = False
        subtopic_match = False
        subtopic_conflict = False
        geography_conflict = False
        event_type_conflict = False
    else:
        components = {
            "title_similarity": evaluation.title_similarity,
            "entity_jaccard": evaluation.entity_jaccard,
            "keyword_jaccard": evaluation.keyword_jaccard,
            "semantic_score": evaluation.semantic_score,
            "entity_overlap_score": evaluation.entity_overlap_score,
            "time_proximity": evaluation.time_proximity,
        }
        overlap_counts = {
            "entity_overlap": evaluation.entity_overlap,
            "key_entity_overlap": evaluation.key_entity_overlap,
            "keyword_overlap": evaluation.keyword_overlap,
            "location_overlap": evaluation.location_overlap,
            "title_token_overlap": evaluation.title_token_overlap,
        }
        selected_score = evaluation.score
        selected_cluster_id = evaluation.cluster.id
        signal_gate_passed = evaluation.signal_gate_passed
        signal_reasons = evaluation.signal_reasons
        candidate_rejection_reason = evaluation.rejection_reason
        article_content_class = evaluation.article_content_class
        cluster_content_class = evaluation.cluster_content_class
        primary_entity_overlap = evaluation.primary_entity_overlap
        title_primary_entity_overlap = evaluation.title_primary_entity_overlap
        near_duplicate_title = evaluation.near_duplicate_title
        same_source_update_chain = evaluation.same_source_update_chain
        primary_entity_conflict = evaluation.primary_entity_conflict
        subtopic_match = evaluation.subtopic_match
        subtopic_conflict = evaluation.subtopic_conflict
        geography_conflict = evaluation.geography_conflict
        event_type_conflict = evaluation.event_type_conflict

    topic_match = evaluation.topic_match if evaluation is not None else False
    selected_topic = evaluation.cluster.topic if evaluation is not None else None
    selected_primary_topic = evaluation.cluster.primary_topic if evaluation is not None else None
    selected_subtopic = evaluation.cluster.subtopic if evaluation is not None else None
    thresholds = {
        "score_threshold": settings.cluster_score_threshold,
        "title_signal_threshold": settings.cluster_min_title_signal,
        "entity_overlap_threshold": settings.cluster_min_entity_overlap,
        "primary_entity_overlap_required": True,
        "keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
        "topic_semantic_score_threshold": settings.cluster_min_topic_semantic_score,
        "attach_override_title_similarity_threshold": settings.cluster_attach_override_min_title_similarity,
        "attach_override_time_proximity_threshold": settings.cluster_attach_override_min_time_proximity,
        "attach_override_keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
    }

    thresholds_met = {
        "score_threshold_met": selected_score >= settings.cluster_score_threshold,
        "title_signal_met": components["title_similarity"] >= settings.cluster_min_title_signal,
        "entity_overlap_met": overlap_counts["entity_overlap"] >= settings.cluster_min_entity_overlap,
        "primary_entity_overlap_met": primary_entity_overlap,
        "title_primary_entity_overlap_met": title_primary_entity_overlap,
        "keyword_overlap_met": overlap_counts["keyword_overlap"] >= settings.cluster_min_keyword_overlap,
        "topic_semantic_score_met": topic_match
        and components["semantic_score"] >= settings.cluster_min_topic_semantic_score,
        "topic_match_met": topic_match,
        "subtopic_match_met": subtopic_match,
        "signal_gate_passed": signal_gate_passed,
        "attach_override_met": attach_override_met,
        "near_duplicate_title_met": near_duplicate_title,
        "same_source_update_chain_met": same_source_update_chain,
        "primary_entity_conflict_met": primary_entity_conflict,
        "subtopic_conflict_met": subtopic_conflict,
        "geography_conflict_met": geography_conflict,
        "event_type_conflict_met": event_type_conflict,
    }

    matched_features: list[str] = []
    ignored_features: list[str] = []
    if topic_match:
        matched_features.append("topic_match")
    else:
        ignored_features.append("topic_mismatch")
    if thresholds_met["title_signal_met"]:
        matched_features.append("title_similarity")
    if thresholds_met["entity_overlap_met"]:
        matched_features.append("entity_overlap")
    if thresholds_met["primary_entity_overlap_met"]:
        matched_features.append("primary_entity_overlap")
    if thresholds_met["keyword_overlap_met"]:
        matched_features.append("keyword_overlap")
    if overlap_counts["location_overlap"] > 0:
        matched_features.append("location_overlap")
    if thresholds_met["near_duplicate_title_met"]:
        matched_features.append("near_duplicate_title")
    if thresholds_met["same_source_update_chain_met"]:
        matched_features.append("same_source_update_chain")
    if thresholds_met["primary_entity_conflict_met"]:
        ignored_features.append("primary_entity_conflict")
    if thresholds_met["subtopic_match_met"]:
        matched_features.append("subtopic_match")
    if thresholds_met["subtopic_conflict_met"]:
        ignored_features.append("subtopic_conflict")
    if thresholds_met["geography_conflict_met"]:
        ignored_features.append("geography_conflict")
    if thresholds_met["event_type_conflict_met"]:
        ignored_features.append("event_type_conflict")
    if components["time_proximity"] > 0:
        if signal_gate_passed:
            matched_features.append("time_proximity_support")
        else:
            ignored_features.append("time_proximity_without_signal")
    if candidate_rejection_reason:
        ignored_features.append(candidate_rejection_reason)

    score_formula = (
        "0.40*title_similarity + 0.20*entity_jaccard + 0.15*keyword_jaccard + "
        "0.15*entity_overlap_score + 0.10*time_proximity"
    )
    semantic_formula = "0.50*title_similarity + 0.30*entity_jaccard + 0.20*keyword_jaccard"

    warnings: list[str] = []
    warnings.extend(reason for reason in source_quality_reasons if reason)
    if decision == "attach_existing_cluster":
        if not signal_gate_passed:
            warnings.append("attached_without_semantic_gate")
        if selected_score < settings.cluster_score_threshold:
            warnings.append("attached_below_score_threshold")
        if components["time_proximity"] >= settings.cluster_attach_override_min_time_proximity and not signal_reasons:
            warnings.append("time_proximity_without_semantic_signal")
        if components["semantic_score"] < settings.cluster_min_topic_semantic_score and not (
            thresholds_met["title_signal_met"]
            or thresholds_met["entity_overlap_met"]
            or thresholds_met["keyword_overlap_met"]
        ):
            warnings.append("low_semantic_score")
        if thresholds_met["primary_entity_overlap_met"] and not thresholds_met["title_primary_entity_overlap_met"]:
            warnings.append("primary_entity_not_in_titles")

    return {
        "decision": decision,
        "decision_reason": decision_reason,
        "candidate_count": candidate_count,
        "selected_cluster_id": selected_cluster_id,
        "selected_topic": selected_topic,
        "selected_primary_topic": selected_primary_topic,
        "selected_subtopic": selected_subtopic,
        "selected_score": round(selected_score, 4),
        "selected_topic_match": topic_match,
        "selected_source_match": evaluation.source_match if evaluation is not None else False,
        "article_content_class": article_content_class,
        "cluster_content_class": cluster_content_class,
        "score_formula": score_formula,
        "semantic_formula": semantic_formula,
        "components": components,
        "overlap_counts": overlap_counts,
        "thresholds": thresholds,
        "thresholds_met": thresholds_met,
        "signal_reasons": list(signal_reasons),
        "matched_features": sorted(set(matched_features)),
        "ignored_features": sorted(set(ignored_features)),
        "source_quality_reasons": list(source_quality_reasons),
        "source_trust": source_trust,
        "candidate_rejection_reason": candidate_rejection_reason,
        "membership_rejection_status": _membership_rejection_status(
            candidate_rejection_reason,
            source_quality_reasons,
            article_content_class,
            decision=decision,
        ),
        "warnings": warnings,
        "attach_override_components": attach_override_components or {},
        "candidate_diagnostics": candidate_diagnostics or [],
    }


def _candidate_diagnostic(
    *,
    article: Article,
    article_features: FeatureVector,
    evaluation: CandidateEvaluation,
    final_decision: str,
    rejection_reason: str | None = None,
) -> dict:
    return {
        "article_headline": article.title,
        "candidate_cluster_headline": evaluation.cluster.headline,
        "article_primary_topic": article_features.primary_topic,
        "article_subtopic": article_features.subtopic,
        "cluster_primary_topic": evaluation.cluster.primary_topic,
        "cluster_subtopic": evaluation.cluster.subtopic,
        "shared_entities": list(evaluation.shared_entities),
        "conflicting_entities": list(evaluation.conflicting_entities),
        "similarity_score": evaluation.score,
        "final_decision": final_decision,
        "rejection_reason": rejection_reason or evaluation.rejection_reason,
    }


def _rebuild_cluster(session: Session, cluster: Cluster, settings: Settings) -> RebuildResult:
    articles_stmt: Select[tuple[Article]] = (
        select(Article)
        .join(ClusterArticle, ClusterArticle.article_id == Article.id)
        .where(ClusterArticle.cluster_id == cluster.id)
        .order_by(Article.published_at.asc(), Article.id.asc())
    )
    articles = list(session.scalars(articles_stmt).all())
    if not articles:
        cluster.status = "hidden"
        cluster.validation_error = "cluster has no source articles"
        cluster.promotion_reason = "no_sources_available"
        cluster.promotion_explanation = "Cluster was hidden because it no longer has any attached source articles."
        cluster.topic = "General"
        return RebuildResult(
            validation_failed=True,
            timeline_deduplicated=0,
            promotion_attempted=False,
            promoted=False,
            promotion_failed=False,
            source_count=0,
            status="hidden",
        )

    first_seen = min(article.published_at for article in articles)
    last_updated = max(article.published_at for article in articles)
    source_count = len(articles)
    previous_status = cluster.status
    promotion_attempted = previous_status == "hidden"

    keyword_union: set[str] = set()
    entity_union: set[str] = set()
    cluster_topics = derive_topic_from_articles(articles)
    primary_topic, subtopic, key_entities, geography, event_type = _cluster_lane_metadata(articles)
    similarity_stmt = select(func.avg(ClusterArticle.similarity_score)).where(ClusterArticle.cluster_id == cluster.id)
    avg_similarity = session.scalar(similarity_stmt) or 0.0

    for article in articles:
        keyword_union.update(_semantic_keywords(article.keywords))
        article_entities = _semantic_entities(article.entities)
        article_key_entities = _semantic_entities(article.key_entities) if article_entities else set()
        entity_union.update(article_entities)
        entity_union.update(article_key_entities)

    cluster.first_seen = first_seen
    cluster.last_updated = last_updated
    cluster.headline = build_headline(cluster.id, articles)
    cluster.summary = build_summary(cluster.id, articles)
    cluster.what_changed = build_what_changed(cluster.id, articles)
    cluster.why_it_matters = build_why_it_matters(cluster.id, articles)
    cluster.key_facts = build_key_facts(cluster.id, articles)
    cluster.normalized_headline = normalize_title(cluster.headline)
    cluster.keywords = sorted(keyword_union)
    cluster.entities = sorted(entity_union)
    cluster.topic = cluster_topics
    cluster.primary_topic = primary_topic
    cluster.subtopic = subtopic
    cluster.key_entities = key_entities
    cluster.geography = geography
    cluster.event_type = event_type
    cluster.score = round(float(avg_similarity), 4)
    cluster.status = build_status(
        source_count=source_count,
        last_updated=last_updated,
        now=datetime.now(timezone.utc),
        stale_hours=settings.cluster_stale_hours,
        emerging_hours=settings.cluster_emerging_hours,
        emerging_source_count=settings.cluster_emerging_source_count,
    )

    timeline_entries, dedup_count = build_timeline_events(
        articles,
        dedupe_window_hours=settings.timeline_dedupe_window_hours,
        dedupe_title_similarity=settings.timeline_dedupe_title_similarity,
    )

    session.query(ClusterTimelineEvent).filter(ClusterTimelineEvent.cluster_id == cluster.id).delete()
    for item in timeline_entries:
        event = ClusterTimelineEvent(
            cluster_id=cluster.id,
            timestamp=item.timestamp,
            event=item.event,
            source_url=item.source_url,
            source_title=item.source_title,
        )
        session.add(event)

    validation = validate_cluster_record(
        cluster,
        source_count=source_count,
        min_sources=settings.cluster_min_sources_for_api,
        min_headline_words=settings.cluster_min_headline_words,
        min_detail_words=settings.cluster_min_detail_words,
    )
    cluster.validation_error = validation.error

    promoted = False
    promotion_failed = False
    promotion_blockers = _promotion_blockers(
        source_count=source_count,
        validation_error=cluster.validation_error,
        settings=settings,
        articles=articles,
    )
    visibility_eligible = not promotion_blockers
    if visibility_eligible:
        if previous_status == "hidden":
            promoted = True
            cluster.previous_status = previous_status
            cluster.promoted_at = datetime.now(timezone.utc)
            cluster.promotion_reason = "source_count_threshold_reached_and_validation_passed"
            cluster.promotion_explanation = (
                f"Promoted after reaching {source_count} sources and passing validation."
            )
    else:
        cluster.previous_status = previous_status
        cluster.status = "hidden"
        cluster.promotion_reason = "; ".join(blocker.split(":", 1)[0] for blocker in promotion_blockers)
        cluster.promotion_explanation = (
            "Cluster remains hidden until it clears these blockers: "
            + "; ".join(promotion_blockers)
        )
        if promotion_attempted:
            promotion_failed = True

    return RebuildResult(
        validation_failed=not validation.is_valid,
        timeline_deduplicated=dedup_count,
        promotion_attempted=promotion_attempted,
        promoted=promoted,
        promotion_failed=promotion_failed,
        source_count=source_count,
        status=cluster.status,
    )


def _attach_article_to_cluster(
    session: Session,
    cluster: Cluster,
    article: Article,
    score: float,
    heuristic_breakdown: dict,
) -> None:
    link = ClusterArticle(
        cluster_id=cluster.id,
        article_id=article.id,
        similarity_score=score,
        heuristic_breakdown=heuristic_breakdown,
    )
    session.add(link)
    session.flush()


def _create_cluster(session: Session, article: Article) -> Cluster:
    topic_classification = apply_topic_classification(article)
    cluster = Cluster(
        id=str(uuid.uuid4()),
        headline="pending headline",
        summary="pending summary",
        what_changed="pending change",
        why_it_matters="pending impact",
        first_seen=article.published_at,
        last_updated=article.published_at,
        score=0.0,
        status="emerging",
        normalized_headline=article.normalized_title,
        keywords=sorted(_semantic_keywords(article.keywords)),
        entities=sorted(_semantic_entities(article.entities)),
        topic=article.topic,
        primary_topic=topic_classification.primary_topic,
        subtopic=topic_classification.subtopic,
        key_entities=list(topic_classification.key_entities),
        geography=topic_classification.geography,
        event_type=topic_classification.event_type,
    )
    session.add(cluster)
    session.flush()
    return cluster


def cluster_new_articles(session: Session, settings: Settings, article_ids: list[int] | None = None) -> ClusteringRunResult:
    created_count = 0
    updated_count = 0
    candidates_evaluated = 0
    signal_rejected = 0
    attach_decisions = 0
    new_decisions = 0
    low_confidence_new = 0
    timeline_deduplicated = 0
    promoted_count = 0
    promotion_attempts = 0
    promotion_failures = 0
    candidates_same_topic = 0
    candidates_cross_topic_rejected = 0
    entity_overlap_attaches = 0
    entity_conflict_rejected = 0
    no_candidate_new = 0
    topic_lane_attaches = 0
    topic_lane_new = 0
    invalid_cluster_ids: set[str] = set()

    batch_size = max(settings.clustering_batch_size, len(article_ids or ()))
    pending = _load_unclustered_articles(session, batch_size, article_ids=article_ids)

    for article in pending:
        article_features = _article_features(article)
        article_quality = evaluate_article_quality(article)
        article.topic = article_features.topic
        candidates = _load_candidate_clusters(session, article, article_features, settings)
        candidates_same_topic += len(candidates)

        best_evaluation: CandidateEvaluation | None = None
        strongest_evaluation: CandidateEvaluation | None = None
        evaluations: list[CandidateEvaluation] = []

        for candidate_cluster in candidates:
            candidates_evaluated += 1
            cluster_features = _cluster_features(candidate_cluster)
            evaluation = _evaluate_candidate(candidate_cluster, article_features, cluster_features, settings)
            evaluations.append(evaluation)

            if _is_better_candidate(evaluation, strongest_evaluation, settings.cluster_tie_break_epsilon):
                strongest_evaluation = evaluation

            if not evaluation.signal_gate_passed:
                signal_rejected += 1
                if evaluation.rejection_reason == "primary_topic_mismatch":
                    candidates_cross_topic_rejected += 1
                if evaluation.primary_entity_conflict:
                    entity_conflict_rejected += 1
                continue

            if _is_better_candidate(evaluation, best_evaluation, settings.cluster_tie_break_epsilon):
                best_evaluation = evaluation

        decision_reason = ""
        chosen_score = 1.0

        if best_evaluation is None:
            cluster = _create_cluster(session, article)
            created_count += 1
            new_decisions += 1
            topic_lane_new += 1
            decision_reason = "no_candidate_clusters" if not candidates else "strongest_candidate_failed_semantic_gate"
            if not candidates:
                no_candidate_new += 1
            diagnostics = [
                _candidate_diagnostic(
                    article=article,
                    article_features=article_features,
                    evaluation=evaluation,
                    final_decision="reject",
                )
                for evaluation in evaluations
            ]
            breakdown = _build_heuristic_breakdown(
                decision="create_new_cluster",
                decision_reason=decision_reason,
                candidate_count=len(candidates),
                settings=settings,
                evaluation=strongest_evaluation,
                source_quality_reasons=article_quality.reasons,
                source_trust=article_quality.source_trust,
                candidate_diagnostics=diagnostics,
            )
        else:
            semantic_override_met = (
                best_evaluation.signal_gate_passed
                and best_evaluation.time_proximity >= settings.cluster_attach_override_min_time_proximity
                and any(
                    reason
                    in {
                        "meaningful_entity_overlap",
                        "meaningful_keyword_overlap",
                        "topic_semantic_similarity",
                        "topic_title_keyword_similarity",
                    }
                    for reason in best_evaluation.signal_reasons
                )
            )
            title_override_met = (
                best_evaluation.signal_gate_passed
                and best_evaluation.title_similarity >= settings.cluster_attach_override_min_title_similarity
                and best_evaluation.time_proximity >= settings.cluster_attach_override_min_time_proximity
                and "strong_title_similarity" in best_evaluation.signal_reasons
            )
            attach_override_met = semantic_override_met or title_override_met
            should_attach = best_evaluation.signal_gate_passed and (
                best_evaluation.score >= settings.cluster_score_threshold or attach_override_met
            )
            attach_override_components = {
                "signal_gate_passed": best_evaluation.signal_gate_passed,
                "signal_reasons": list(best_evaluation.signal_reasons),
                "topic_match": best_evaluation.topic_match,
                "keyword_overlap": best_evaluation.keyword_overlap,
                "keyword_overlap_threshold": settings.cluster_min_keyword_overlap,
                "title_similarity": best_evaluation.title_similarity,
                "title_similarity_threshold": settings.cluster_attach_override_min_title_similarity,
                "semantic_score": best_evaluation.semantic_score,
                "topic_semantic_score_threshold": settings.cluster_min_topic_semantic_score,
                "time_proximity": best_evaluation.time_proximity,
                "time_proximity_threshold": settings.cluster_attach_override_min_time_proximity,
            }

            if should_attach:
                cluster = best_evaluation.cluster
                chosen_score = best_evaluation.score
                attach_decisions += 1
                topic_lane_attaches += 1
                if best_evaluation.entity_overlap > 0:
                    entity_overlap_attaches += 1
                decision_reason = (
                    "attached_to_existing_cluster_via_override"
                    if attach_override_met and best_evaluation.score < settings.cluster_score_threshold
                    else "attached_to_existing_cluster"
                )
                diagnostics = [
                    _candidate_diagnostic(
                        article=article,
                        article_features=article_features,
                        evaluation=evaluation,
                        final_decision="attach" if evaluation.cluster.id == best_evaluation.cluster.id else "reject",
                        rejection_reason=None
                        if evaluation.cluster.id == best_evaluation.cluster.id
                        else evaluation.rejection_reason or "lower_ranked_candidate",
                    )
                    for evaluation in evaluations
                ]
                breakdown = _build_heuristic_breakdown(
                    decision="attach_existing_cluster",
                    decision_reason=decision_reason,
                    candidate_count=len(candidates),
                    settings=settings,
                    evaluation=best_evaluation,
                    attach_override_met=attach_override_met,
                    attach_override_components=attach_override_components,
                    source_quality_reasons=article_quality.reasons,
                    source_trust=article_quality.source_trust,
                    candidate_diagnostics=diagnostics,
                )
            else:
                cluster = _create_cluster(session, article)
                created_count += 1
                new_decisions += 1
                topic_lane_new += 1
                low_confidence_new += 1
                decision_reason = "best_candidate_below_score_threshold_and_no_safe_override"
                diagnostics = [
                    _candidate_diagnostic(
                        article=article,
                        article_features=article_features,
                        evaluation=evaluation,
                        final_decision="create" if evaluation.cluster.id == best_evaluation.cluster.id else "reject",
                        rejection_reason=(
                            decision_reason
                            if evaluation.cluster.id == best_evaluation.cluster.id
                            else evaluation.rejection_reason or "lower_ranked_candidate"
                        ),
                    )
                    for evaluation in evaluations
                ]
                breakdown = _build_heuristic_breakdown(
                    decision="create_new_cluster",
                    decision_reason=decision_reason,
                    candidate_count=len(candidates),
                    settings=settings,
                    evaluation=best_evaluation,
                    attach_override_met=attach_override_met,
                    attach_override_components=attach_override_components,
                    source_quality_reasons=article_quality.reasons,
                    source_trust=article_quality.source_trust,
                    candidate_diagnostics=diagnostics,
                )

        _attach_article_to_cluster(session, cluster, article, chosen_score, breakdown)
        log_payload = {
            "article_id": article.id,
            "article_title": article.title,
            "decision": breakdown["decision"],
            "reason": decision_reason,
            "selected_cluster_id": cluster.id,
            "candidate_cluster_id": breakdown["selected_cluster_id"],
            "strongest_candidate_cluster_id": breakdown["selected_cluster_id"],
            "strongest_candidate_topic": breakdown["selected_topic"],
            "strongest_candidate_primary_topic": breakdown["selected_primary_topic"],
            "strongest_candidate_subtopic": breakdown["selected_subtopic"],
            "final_score": chosen_score,
            "candidate_score": breakdown["selected_score"],
            "title_similarity": breakdown["components"]["title_similarity"],
            "entity_jaccard": breakdown["components"]["entity_jaccard"],
            "keyword_jaccard": breakdown["components"]["keyword_jaccard"],
            "semantic_score": breakdown["components"]["semantic_score"],
            "entity_overlap": breakdown["overlap_counts"]["entity_overlap"],
            "keyword_overlap": breakdown["overlap_counts"]["keyword_overlap"],
            "location_overlap": breakdown["overlap_counts"]["location_overlap"],
            "title_token_overlap": breakdown["overlap_counts"]["title_token_overlap"],
            "source_match": breakdown["selected_source_match"],
            "topic_match": breakdown["selected_topic_match"],
            "subtopic_match": breakdown["thresholds_met"]["subtopic_match_met"],
            "primary_entity_overlap": breakdown["thresholds_met"]["primary_entity_overlap_met"],
            "title_primary_entity_overlap": breakdown["thresholds_met"]["title_primary_entity_overlap_met"],
            "near_duplicate_title": breakdown["thresholds_met"]["near_duplicate_title_met"],
            "same_source_update_chain": breakdown["thresholds_met"]["same_source_update_chain_met"],
            "subtopic_conflict": breakdown["thresholds_met"]["subtopic_conflict_met"],
            "geography_conflict": breakdown["thresholds_met"]["geography_conflict_met"],
            "event_type_conflict": breakdown["thresholds_met"]["event_type_conflict_met"],
            "time_proximity": breakdown["components"]["time_proximity"],
            "signal_gate_passed": breakdown["thresholds_met"]["signal_gate_passed"],
            "signal_reasons": breakdown["signal_reasons"],
            "matched_features": breakdown["matched_features"],
            "ignored_features": breakdown["ignored_features"],
            "warnings": breakdown["warnings"],
            "source_quality_reasons": breakdown["source_quality_reasons"],
            "source_trust": breakdown["source_trust"],
            "article_content_class": breakdown["article_content_class"],
            "cluster_content_class": breakdown["cluster_content_class"],
            "membership_rejection_status": breakdown["membership_rejection_status"],
        }
        logger.info(
            "cluster_article_decision %s",
            json.dumps(log_payload, sort_keys=True, default=str),
        )
        rebuild_result = _rebuild_cluster(session, cluster, settings)
        if rebuild_result.validation_failed:
            invalid_cluster_ids.add(cluster.id)
        promotion_attempts += int(rebuild_result.promotion_attempted)
        promoted_count += int(rebuild_result.promoted)
        promotion_failures += int(rebuild_result.promotion_failed)

        updated_count += 1
        timeline_deduplicated += rebuild_result.timeline_deduplicated

    for cluster in _load_repromotable_hidden_clusters(session, settings):
        rebuild_result = _rebuild_cluster(session, cluster, settings)
        promotion_attempts += int(rebuild_result.promotion_attempted)
        promoted_count += int(rebuild_result.promoted)
        promotion_failures += int(rebuild_result.promotion_failed)
        if rebuild_result.validation_failed:
            invalid_cluster_ids.add(cluster.id)

    _refresh_related_clusters(session, settings)

    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    total_clusters = int(session.scalar(select(func.count()).select_from(Cluster)) or 0)
    active_total = int(
        session.scalar(
            select(func.count())
            .select_from(Cluster)
            .where(
                Cluster.status != "hidden",
                Cluster.validation_error.is_(None),
                source_count_subquery >= settings.cluster_min_sources_for_api,
            )
        )
        or 0
    )
    hidden_total = max(0, total_clusters - active_total)

    return ClusteringRunResult(
        created_count=created_count,
        updated_count=updated_count,
        candidates_evaluated=candidates_evaluated,
        signal_rejected=signal_rejected,
        attach_decisions=attach_decisions,
        new_decisions=new_decisions,
        low_confidence_new=low_confidence_new,
        validation_rejected=len(invalid_cluster_ids),
        timeline_deduplicated=timeline_deduplicated,
        promoted_count=promoted_count,
        hidden_total=hidden_total,
        active_total=active_total,
        promotion_attempts=promotion_attempts,
        promotion_failures=promotion_failures,
        candidates_same_topic=candidates_same_topic,
        candidates_cross_topic_rejected=candidates_cross_topic_rejected,
        entity_overlap_attaches=entity_overlap_attaches,
        entity_conflict_rejected=entity_conflict_rejected,
        no_candidate_new=no_candidate_new,
        topic_lane_attaches=topic_lane_attaches,
        topic_lane_new=topic_lane_new,
    )
