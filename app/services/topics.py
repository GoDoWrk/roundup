from __future__ import annotations

import re
from collections import Counter

from app.db.models import Article

STOPWORDS = {
    "about",
    "after",
    "also",
    "against",
    "among",
    "because",
    "before",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
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

_TOPIC_BLOCKLIST = {
    "analysis",
    "agencies",
    "agency",
    "announced",
    "announces",
    "breaking",
    "breaking news",
    "city",
    "commuter",
    "council",
    "department",
    "expand",
    "expanded",
    "expands",
    "feature",
    "group",
    "live",
    "leaders",
    "mayor",
    "news",
    "officials",
    "police",
    "publish",
    "publishes",
    "report",
    "reporting",
    "react",
    "reacts",
    "regional",
    "state",
    "update",
    "video",
    "world news",
    "eu",
    "u k",
    "u s",
    "uk",
    "un",
    "us",
}

_REPORTING_VERBS = {
    "added",
    "announces",
    "announced",
    "arrested",
    "charged",
    "cuts",
    "expanded",
    "expands",
    "investigates",
    "investigating",
    "look",
    "looks",
    "probes",
    "probe",
    "publishes",
    "publishing",
    "reacts",
    "reported",
    "reports",
    "says",
    "warns",
}

_ACTION_BREAKERS = {
    "adds",
    "added",
    "announce",
    "announces",
    "announced",
    "arrest",
    "arrests",
    "arrested",
    "approve",
    "approves",
    "approved",
    "charges",
    "charged",
    "charge",
    "cuts",
    "cut",
    "expand",
    "expands",
    "expanded",
    "investigate",
    "investigates",
    "investigated",
    "look",
    "looks",
    "looked",
    "probe",
    "probes",
    "probed",
    "publish",
    "publishes",
    "published",
    "react",
    "reacts",
    "reacted",
    "report",
    "reports",
    "reported",
    "say",
    "says",
    "said",
    "warn",
    "warns",
    "wins",
    "won",
}

_TOPIC_CONNECTORS = {
    "about",
    "against",
    "as",
    "at",
    "after",
    "before",
    "by",
    "between",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "over",
    "through",
    "to",
    "under",
    "via",
    "with",
}

_TOPIC_PREFIXES = {
    "alleged",
    "almost",
    "current",
    "earlier",
    "first",
    "latest",
    "new",
    "odd",
    "possible",
    "possibly",
    "reported",
    "reportedly",
    "second",
    "suspected",
    "tentative",
    "using",
    "weird",
}

_TOPIC_ANCHORS = {
    "agency",
    "agencies",
    "city",
    "council",
    "department",
    "eu",
    "french",
    "group",
    "leaders",
    "local",
    "mayor",
    "news",
    "officials",
    "police",
    "regional",
    "state",
    "uk",
    "un",
    "us",
}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_keywords(text: str, max_keywords: int = 12) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:max_keywords]]


def _normalize_topic_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalize_whitespace(value).lower()))


def _is_generic_topic(value: str) -> bool:
    topic_key = _normalize_topic_key(value)
    return not topic_key or topic_key in _TOPIC_BLOCKLIST


def _entity_candidates(text: str) -> list[str]:
    matches = re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)
    seen: set[str] = set()
    ordered: list[str] = []
    for match in matches:
        term = normalize_whitespace(match.group(0))
        if not term or term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered


def _topic_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9\-']*", text)


def _split_topic_chunks(title: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []

    for token in _topic_tokens(title):
        normalized = _normalize_topic_key(token)
        if normalized in _ACTION_BREAKERS or normalized in _TOPIC_CONNECTORS:
            if current:
                chunks.append(current)
                current = []
            continue

        if normalized in {"a", "an", "and", "the", "or", "but", "so"}:
            continue

        current.append(token)

    if current:
        chunks.append(current)

    return chunks


def _strip_topic_prefixes(tokens: list[str]) -> list[str]:
    trimmed = list(tokens)
    while len(trimmed) > 1 and _normalize_topic_key(trimmed[0]) in _TOPIC_PREFIXES:
        trimmed.pop(0)
    return trimmed


def _chunk_score(tokens: list[str]) -> tuple[int, int]:
    meaningful = [token for token in tokens if _normalize_topic_key(token) not in _TOPIC_PREFIXES]
    if not meaningful:
        return (0, 0)
    entity_bonus = 1 if any(token[:1].isupper() for token in meaningful) else 0
    return (len(meaningful), entity_bonus)


def _leading_subject_phrase(title: str) -> str:
    chunks = _split_topic_chunks(title)
    if not chunks:
        return ""

    best_index = 0
    best_score = (-1, -1)
    for index, chunk in enumerate(chunks):
        score = _chunk_score(chunk)
        if score > best_score or (score == best_score and index > best_index):
            best_score = score
            best_index = index

    tokens = _strip_topic_prefixes(chunks[best_index])
    if not tokens:
        return ""

    if len(tokens) < 3 and best_index > 0:
        previous_chunk = chunks[best_index - 1]
        for token in previous_chunk:
            normalized = _normalize_topic_key(token)
            if normalized in _TOPIC_ANCHORS or normalized in _TOPIC_PREFIXES:
                continue
            if len(normalized) <= 3:
                continue
            if token not in tokens:
                tokens = [token, *tokens]
                break

    return " ".join(tokens[:4])


def derive_topic_from_text(title: str, content_text: str = "") -> str:
    combined = f"{normalize_whitespace(title)} {normalize_whitespace(content_text[:2000])}".strip()
    if not combined:
        return "General"

    leading_subject = _leading_subject_phrase(title)
    if leading_subject and not _is_generic_topic(leading_subject):
        return leading_subject

    keywords = [keyword for keyword in extract_keywords(combined, max_keywords=6) if not _is_generic_topic(keyword)]
    if len(keywords) >= 2:
        return f"{keywords[0].title()} {keywords[1].title()}"
    if keywords:
        return keywords[0].title()

    entity_candidates = [
        term for term in _entity_candidates(combined) if not _is_generic_topic(term) and len(term.split()) <= 2
    ]
    if entity_candidates:
        return entity_candidates[0]

    fallback_words = [word for word in re.findall(r"[A-Za-z0-9]+", normalize_whitespace(title)) if len(word) > 2]
    if fallback_words:
        return " ".join(word.title() for word in fallback_words[:3])
    return "General"


def derive_topic_from_article(article: Article) -> str:
    source_article = getattr(article, "article", None)
    if source_article is not None:
        return derive_topic_from_article(source_article)

    stored_topic = normalize_whitespace(getattr(article, "topic", ""))
    if stored_topic:
        return stored_topic
    return derive_topic_from_text(article.title, article.content_text)


def derive_topic_from_articles(articles: list[Article]) -> str:
    if not articles:
        return "General"

    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for index, article in enumerate(articles):
        topic = derive_topic_from_article(article)
        counts[topic] += 1
        first_seen.setdefault(topic, index)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], first_seen[item[0]], item[0].lower()))
    return ranked[0][0] if ranked else "General"


def topic_matches(left: str, right: str) -> bool:
    left_key = _normalize_topic_key(left)
    right_key = _normalize_topic_key(right)
    if left_key == right_key:
        return True

    left_terms = set(left_key.split())
    right_terms = set(right_key.split())
    if not left_terms or not right_terms:
        return False

    shared_terms = left_terms.intersection(right_terms)
    return bool(shared_terms - _TOPIC_BLOCKLIST)
