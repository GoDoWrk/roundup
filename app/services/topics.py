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
    "attack",
    "attacks",
    "attacked",
    "attacking",
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

_TOPIC_SUFFIXES = {
    "added",
    "announcement",
    "announcements",
    "coverage",
    "details",
    "detail",
    "first",
    "funding",
    "latest",
    "live",
    "move",
    "moves",
    "news",
    "plan",
    "plans",
    "report",
    "reporting",
    "release",
    "releases",
    "story",
    "timeline",
    "update",
    "updates",
    "vote",
    "votes",
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

_THEME_RULES: list[tuple[str, set[str]]] = [
    (
        "War",
        {
            "war",
            "wars",
            "battle",
            "battles",
            "conflict",
            "conflicts",
            "crisis",
            "crises",
            "hostilities",
            "strike",
            "strikes",
            "ceasefire",
            "cease-fire",
            "truce",
            "military",
        },
    ),
    (
        "Files",
        {
            "file",
            "files",
            "records",
            "documents",
            "transparency",
        },
    ),
    (
        "Admin",
        {
            "admin",
            "administration",
            "administrations",
        },
    ),
    (
        "Expansion",
        {
            "expand",
            "expands",
            "expanded",
            "expansion",
        },
    ),
    (
        "Plan",
        {
            "plan",
            "plans",
            "proposal",
            "roadmap",
            "blueprint",
            "timeline",
        },
    ),
    (
        "Deal",
        {
            "deal",
            "deals",
            "agreement",
            "package",
        },
    ),
    (
        "Bill",
        {
            "bill",
            "bills",
            "funding",
            "legislation",
            "resolution",
        },
    ),
    (
        "Election",
        {
            "election",
            "elections",
            "vote",
            "votes",
            "voting",
            "poll",
            "polls",
        },
    ),
]

_THEME_SUBJECT_PRIORITY: dict[str, list[str]] = {
    "War": [
        "Iran",
        "Israel",
        "Ukraine",
        "Russia",
        "Lebanon",
        "Syria",
        "Gaza",
        "Yemen",
        "Sudan",
        "Taiwan",
        "China",
    ],
    "Files": [
        "Epstein",
        "Jeffrey Epstein",
    ],
    "Admin": [
        "Trump",
        "Biden",
        "Harris",
        "Obama",
        "Modi",
        "Netanyahu",
        "Starmer",
        "Mamdani",
    ],
}

_TOPIC_NOISE_WORDS = {
    "alleged",
    "breaking",
    "classified",
    "current",
    "facing",
    "global",
    "involved",
    "latest",
    "long awaited",
    "longawaited",
    "major",
    "intensify",
    "intensifies",
    "intensifying",
    "misleading",
    "new",
    "news",
    "odd",
    "people",
    "person",
    "preview",
    "race",
    "bet",
    "bets",
    "k",
    "winning",
    "unveils",
    "reported",
    "reportedly",
    "reporting",
    "soldier",
    "story",
    "tech",
    "used",
    "using",
    "upending",
    "year",
    "years",
    "live",
}

_GENERIC_ENTITY_HINTS = {
    "australia",
    "china",
    "e u",
    "eu",
    "french",
    "france",
    "north america",
    "south america",
    "u k",
    "u s",
    "uk",
    "us",
}

_TOPIC_THEME_WORDS = {"war", "files", "admin"}


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


def _normalized_tokens(text: str) -> list[str]:
    return [_normalize_topic_key(token) for token in _topic_tokens(text)]


def _candidate_subject_entities(title: str, content_text: str) -> list[str]:
    combined = f"{normalize_whitespace(title)} {normalize_whitespace(content_text[:2000])}".strip()
    entities = _entity_candidates(combined)
    return [term for term in entities if not _is_generic_topic(term)]


def _display_topic_token(token: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", token)
    if not cleaned:
        return ""
    if cleaned.lower().endswith("s") and len(cleaned) > 3 and token.lower().endswith(("'s", "’s")):
        cleaned = cleaned[:-1]
    if cleaned.isupper() or cleaned.isdigit():
        return cleaned
    if len(cleaned) <= 3 and cleaned.upper() == cleaned:
        return cleaned.upper()
    if any(ch.isupper() for ch in cleaned[1:]):
        return cleaned[0].upper() + cleaned[1:]
    return cleaned[:1].upper() + cleaned[1:].lower()


def _is_topic_noise_token(token: str) -> bool:
    normalized = _normalize_topic_key(token)
    return (
        not normalized
        or len(normalized) <= 1
        or re.fullmatch(r"v\d+", normalized) is not None
        or normalized in STOPWORDS
        or normalized in _TOPIC_BLOCKLIST
        or _is_generic_entity_hint(token)
        or normalized in _TOPIC_PREFIXES
        or normalized in _TOPIC_SUFFIXES
        or normalized in _REPORTING_VERBS
        or normalized in _ACTION_BREAKERS
        or normalized in _TOPIC_NOISE_WORDS
    )


def _is_generic_entity_hint(token: str) -> bool:
    normalized = _normalize_topic_key(token)
    variants = {normalized, normalized.replace(" ", "")}
    if normalized.endswith(" s"):
        stem = " ".join(normalized.split()[:-1])
        variants.add(stem)
        variants.add(stem.replace(" ", ""))
    return bool(variants.intersection(_GENERIC_ENTITY_HINTS))


def _is_strong_topic_token(token: str) -> bool:
    normalized = _normalize_topic_key(token)
    if _is_topic_noise_token(token):
        return False
    if token[:1].isupper() and not _is_generic_entity_hint(token):
        return True
    return len(normalized) > 4 and not _is_generic_entity_hint(token)


def _clean_topic_tokens(tokens: list[str]) -> list[str]:
    cleaned = [token for token in tokens if not _is_topic_noise_token(token)]
    if cleaned:
        return cleaned
    return [token for token in tokens if _normalize_topic_key(token)]


def _topic_phrase_from_tokens(tokens: list[str]) -> str:
    cleaned = _clean_topic_tokens(tokens)
    if not cleaned:
        return ""
    return " ".join(
        display
        for display in (_display_topic_token(token) for token in cleaned[:2])
        if display
    )


def _topic_quality_score(value: str) -> tuple[int, int, int]:
    tokens = _topic_tokens(value)
    cleaned = _clean_topic_tokens(tokens)
    if not cleaned:
        return (0, 0, 0)
    strong_count = sum(1 for token in cleaned if _is_strong_topic_token(token))
    generic_penalty = 1 if any(_is_generic_entity_hint(token) for token in cleaned) else 0
    theme_penalty = 1 if _normalize_topic_key(cleaned[-1]) in _TOPIC_THEME_WORDS and len(cleaned) == 2 else 0
    return (strong_count, len(cleaned) - generic_penalty - theme_penalty, -generic_penalty)


def _identify_theme(normalized_tokens: list[str]) -> str:
    token_set = set(normalized_tokens)
    for theme, markers in _THEME_RULES:
        if token_set.intersection(markers):
            return theme
    return ""


def _select_subject(theme: str, entities: list[str], normalized_tokens: list[str]) -> str:
    priority = _THEME_SUBJECT_PRIORITY.get(theme, [])
    normalized_entities = {entity: _normalize_topic_key(entity) for entity in entities}

    for preferred in priority:
        preferred_key = _normalize_topic_key(preferred)
        for entity, entity_key in normalized_entities.items():
            if preferred_key == entity_key or preferred_key in entity_key or entity_key in preferred_key:
                return entity

    if theme == "Files":
        for entity in entities:
            if "epstein" in _normalize_topic_key(entity):
                return entity

    if theme == "Admin":
        for entity in entities:
            if "trump" in _normalize_topic_key(entity):
                return entity

    if theme == "War":
        war_subjects = set(_THEME_SUBJECT_PRIORITY["War"])
        for entity in entities:
            entity_key = _normalize_topic_key(entity)
            if entity_key in {_normalize_topic_key(subject) for subject in war_subjects}:
                return entity
            if any(subject.lower() in entity_key for subject in war_subjects):
                return entity

    if entities:
        return entities[0]

    topic_words = [token for token in normalized_tokens if len(token) > 2 and token not in STOPWORDS]
    if topic_words:
        return topic_words[0].title()

    return ""


def _theme_candidate_phrase(theme: str, title: str, content_text: str) -> str:
    if theme == "War":
        title_tokens = _normalized_tokens(title)
        if "iran" in title_tokens:
            return "Iran War"
        if "ukraine" in title_tokens:
            return "Ukraine War"
        if "israel" in title_tokens:
            return "Israel War"

    if theme == "Files":
        title_tokens = _normalized_tokens(title)
        if "epstein" in title_tokens:
            return "Epstein Files"

    if theme == "Admin":
        title_tokens = _normalized_tokens(title)
        if "trump" in title_tokens:
            return "Trump Admin"

    return theme


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


def _chunk_score(tokens: list[str]) -> tuple[int, int, int]:
    meaningful = _clean_topic_tokens(tokens)
    if not meaningful:
        return (0, 0, 0)
    entity_bonus = 1 if any(_is_strong_topic_token(token) for token in meaningful) else 0
    return (entity_bonus, sum(1 for token in meaningful if _is_strong_topic_token(token)), len(meaningful))


def _best_topic_phrase(title: str) -> str:
    chunks = _split_topic_chunks(title)
    if not chunks:
        return ""

    best_index = -1
    best_tokens: list[str] = []
    best_score: tuple[int, int, int] = (0, 0, 0)

    for index, chunk in enumerate(chunks):
        tokens = _strip_topic_prefixes(chunk)
        while len(tokens) > 1 and _normalize_topic_key(tokens[-1]) in _TOPIC_SUFFIXES:
            tokens.pop()
        if not tokens:
            continue
        score = _chunk_score(tokens)
        if score > best_score:
            best_index = index
            best_tokens = tokens
            best_score = score

    if not best_tokens:
        return ""

    phrase_tokens = _clean_topic_tokens(best_tokens)
    if len(phrase_tokens) < 2 and len(chunks) > 1:
        for neighbor_index in range(best_index + 1, len(chunks)):
            neighbor_tokens = _clean_topic_tokens(_strip_topic_prefixes(chunks[neighbor_index]))
            extra = next(
                (
                    token
                    for token in neighbor_tokens
                    if _is_strong_topic_token(token) and _normalize_topic_key(token) not in {_normalize_topic_key(existing) for existing in phrase_tokens}
                ),
                "",
            )
            if extra:
                phrase_tokens.append(extra)
                break
        if len(phrase_tokens) < 2:
            for neighbor_index in range(best_index - 1, -1, -1):
                neighbor_tokens = _clean_topic_tokens(_strip_topic_prefixes(chunks[neighbor_index]))
                extra = next(
                    (
                        token
                        for token in neighbor_tokens
                        if _is_strong_topic_token(token) and _normalize_topic_key(token) not in {_normalize_topic_key(existing) for existing in phrase_tokens}
                    ),
                    "",
                )
                if extra:
                    phrase_tokens.append(extra)
                    break

    return _topic_phrase_from_tokens(phrase_tokens)


def derive_topic_from_text(
    title: str,
    content_text: str = "",
    *,
    keywords: list[str] | None = None,
    entities: list[str] | None = None,
) -> str:
    combined = f"{normalize_whitespace(title)} {normalize_whitespace(content_text[:2000])}".strip()
    if not combined:
        return "General"

    normalized_tokens = _normalized_tokens(combined)
    entity_candidates = _candidate_subject_entities(title, content_text)
    if entities:
        merged_entities: list[str] = []
        seen_entities: set[str] = set()
        for candidate in [*entities, *entity_candidates]:
            candidate = normalize_whitespace(candidate)
            if not candidate:
                continue
            normalized_candidate = _normalize_topic_key(candidate)
            if normalized_candidate in seen_entities:
                continue
            seen_entities.add(normalized_candidate)
            merged_entities.append(candidate)
        entity_candidates = merged_entities

    theme = _identify_theme(normalized_tokens)
    if theme in {"War", "Files", "Admin"}:
        themed = _theme_candidate_phrase(theme, title, content_text)
        if themed != theme:
            return themed
        subject = _select_subject(theme, entity_candidates, normalized_tokens)
        if subject:
            return f"{subject} {theme}"

    leading_subject = _best_topic_phrase(title)
    if leading_subject and not _is_generic_topic(leading_subject):
        return leading_subject

    keyword_source = keywords if keywords is not None else extract_keywords(combined, max_keywords=8)
    keyword_candidates = [keyword for keyword in keyword_source if not _is_generic_topic(keyword)]
    if len(keyword_candidates) >= 2:
        return f"{keyword_candidates[0].title()} {keyword_candidates[1].title()}"
    if keyword_candidates:
        return keyword_candidates[0].title()

    if entity_candidates:
        if len(entity_candidates) >= 2:
            return f"{entity_candidates[0]} {entity_candidates[1]}"
        return entity_candidates[0]

    fallback_words = [word for word in re.findall(r"[A-Za-z0-9]+", normalize_whitespace(title)) if len(word) > 2]
    if fallback_words:
        return " ".join(word.title() for word in fallback_words[:2])
    return "General"


def derive_topic_from_article(article: Article) -> str:
    source_article = getattr(article, "article", None)
    if source_article is not None:
        return derive_topic_from_article(source_article)

    recomputed_topic = derive_topic_from_text(
        article.title,
        article.content_text,
        keywords=list(getattr(article, "keywords", []) or []),
        entities=list(getattr(article, "entities", []) or []),
    )
    stored_topic = normalize_whitespace(getattr(article, "topic", ""))
    if stored_topic:
        if _topic_quality_score(recomputed_topic) > _topic_quality_score(stored_topic):
            return recomputed_topic
        return stored_topic
    return recomputed_topic


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
