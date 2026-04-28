from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

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
    "allow",
    "allows",
    "allowing",
    "announce",
    "announces",
    "announced",
    "arrest",
    "arrests",
    "arrested",
    "ban",
    "bans",
    "banned",
    "block",
    "blocks",
    "blocking",
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
    "come",
    "comes",
    "coming",
    "expand",
    "expands",
    "expanded",
    "felt",
    "feel",
    "feels",
    "help",
    "helps",
    "helping",
    "hit",
    "hits",
    "hitting",
    "investigate",
    "investigates",
    "investigated",
    "look",
    "looks",
    "looked",
    "probe",
    "probes",
    "probed",
    "mull",
    "mulls",
    "mulling",
    "mock",
    "mocks",
    "mocked",
    "order",
    "orders",
    "ordering",
    "publish",
    "publishes",
    "published",
    "react",
    "reacts",
    "reacted",
    "reject",
    "rejects",
    "rejected",
    "report",
    "reports",
    "reported",
    "set",
    "sets",
    "setting",
    "say",
    "says",
    "said",
    "tell",
    "tells",
    "told",
    "warn",
    "warns",
    "versus",
    "vs",
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
    "extremely",
    "be",
    "being",
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
    "largest",
    "ever",
    "unelected",
    "frustrating",
    "is",
    "are",
    "was",
    "were",
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
    "outside",
    "like",
    "test",
    "what",
    "year",
    "years",
    "live",
}

_GENERIC_ENTITY_HINTS = {
    "australia",
    "britain",
    "china",
    "e u",
    "eu",
    "europe",
    "french",
    "france",
    "india",
    "north america",
    "south america",
    "u k",
    "u s",
    "uk",
    "us",
    "bbc",
    "guardian",
    "npr",
    "nyt",
    "reuters",
    "al jazeera",
    "ap",
    "afp",
}

_TOPIC_THEME_WORDS = {"war", "files", "admin"}

PRIMARY_TOPICS = ("World", "U.S.", "Politics", "Business", "Technology", "Science", "Health")

SUBTOPICS_BY_PRIMARY_TOPIC: dict[str, tuple[str, ...]] = {
    "Politics": (
        "elections",
        "courts",
        "congress",
        "white_house",
        "redistricting",
        "political_violence",
    ),
    "Technology": (
        "artificial_intelligence",
        "cybersecurity",
        "platforms",
        "devices",
        "regulation",
    ),
    "World": (
        "middle_east",
        "europe",
        "asia",
        "ukraine_russia",
        "humanitarian_crisis",
    ),
    "Business": (
        "markets",
        "inflation",
        "energy",
        "labor",
        "corporate_earnings",
    ),
    "Health": (
        "public_health",
        "medicine",
        "food_drug_safety",
        "insurance",
    ),
    "Science": (
        "climate",
        "space",
        "research",
        "environment",
    ),
}


@dataclass(frozen=True)
class TopicClassification:
    primary_topic: str
    subtopic: str | None
    key_entities: tuple[str, ...]
    geography: str | None
    event_type: str | None


_US_STATE_TERMS = {
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
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
}

_WORLD_GEO_TERMS = {
    "afghanistan",
    "africa",
    "asia",
    "australia",
    "britain",
    "canada",
    "china",
    "europe",
    "france",
    "gaza",
    "germany",
    "india",
    "iran",
    "iraq",
    "israel",
    "japan",
    "lebanon",
    "middle east",
    "nato",
    "russia",
    "sudan",
    "syria",
    "taiwan",
    "ukraine",
    "united kingdom",
    "yemen",
}

_PRIMARY_TOPIC_RULES: list[tuple[str, set[str]]] = [
    ("Health", {"covid", "disease", "health", "hospital", "medicine", "medical", "drug", "fda", "vaccine", "cancer", "doctor", "public health", "insurance", "alzheimer", "asthma", "patient", "patients", "pharma"}),
    ("Science", {"climate", "space", "nasa", "research", "scientists", "science", "environment", "emissions", "species", "wildlife", "planet", "weather"}),
    ("Technology", {"ai", "artificial intelligence", "openai", "deepseek", "cyber", "cybersecurity", "hack", "data breach", "platform", "meta", "google", "apple", "device", "chip", "software", "technology", "tech"}),
    ("Business", {"business", "markets", "stocks", "inflation", "federal reserve", "fed", "earnings", "company", "corporate", "labor", "jobs", "energy", "oil", "gas", "tariff", "economy"}),
    ("Politics", {"election", "elections", "campaign", "vote", "voting", "poll", "court", "supreme court", "judge", "congress", "senate", "sen", "senator", "house", "white house", "president", "trump", "biden", "desantis", "ben sasse", "sasse", "redistricting", "gerrymander", "political"}),
    ("World", _WORLD_GEO_TERMS | {"war", "ceasefire", "humanitarian", "refugee", "foreign", "international"}),
    ("U.S.", {"u.s.", "us", "usa", "united states", "america", "american", "state", "governor", "mayor", "police", "city", "county", "transit", "agency", "board", "museum", "officials", "dam", "evacuation", "emergency", "phoenix"}),
]

_SUBTOPIC_RULES: dict[str, list[tuple[str, set[str]]]] = {
    "Politics": [
        ("redistricting", {"redistricting", "gerrymander", "map", "maps", "district"}),
        ("political_violence", {"shooting", "attack", "assassination", "bomb", "threat", "violence"}),
        ("white_house", {"white house", "president", "administration"}),
        ("congress", {"congress", "senate", "house", "speaker", "lawmakers", "capitol"}),
        ("courts", {"court", "courts", "judge", "lawsuit", "trial", "ruling", "supreme court"}),
        ("elections", {"election", "elections", "campaign", "vote", "voting", "poll", "ballot"}),
    ],
    "Technology": [
        ("cybersecurity", {"cyber", "cybersecurity", "hack", "hacked", "breach", "ransomware", "malware"}),
        ("artificial_intelligence", {"ai", "artificial intelligence", "openai", "chatgpt", "deepseek", "model", "llm"}),
        ("regulation", {"regulation", "regulator", "rules", "antitrust", "ban", "privacy", "lawmakers"}),
        ("platforms", {"platform", "platforms", "meta", "facebook", "instagram", "x", "tiktok", "youtube"}),
        ("devices", {"device", "devices", "iphone", "android", "chip", "semiconductor", "hardware"}),
    ],
    "World": [
        ("ukraine_russia", {"ukraine", "russia", "putin", "kyiv", "moscow"}),
        ("middle_east", {"gaza", "israel", "iran", "iraq", "lebanon", "syria", "yemen", "middle east", "hamas", "hezbollah"}),
        ("humanitarian_crisis", {"humanitarian", "famine", "refugee", "aid", "displaced", "civilians"}),
        ("europe", {"europe", "eu", "uk", "britain", "france", "germany", "nato"}),
        ("asia", {"china", "india", "japan", "taiwan", "korea", "pakistan"}),
    ],
    "Business": [
        ("inflation", {"inflation", "prices", "consumer price", "cpi", "federal reserve", "fed", "rates"}),
        ("corporate_earnings", {"earnings", "profit", "revenue", "quarterly", "guidance"}),
        ("markets", {"market", "markets", "stocks", "shares", "bond", "yield", "dow", "nasdaq"}),
        ("energy", {"energy", "oil", "gas", "electricity", "power", "opec"}),
        ("labor", {"labor", "jobs", "workers", "union", "strike", "wages"}),
    ],
    "Health": [
        ("food_drug_safety", {"fda", "recall", "contamination", "food safety", "drug safety", "side effect"}),
        ("public_health", {"public health", "outbreak", "covid", "vaccine", "pandemic", "disease"}),
        ("medicine", {"medicine", "medical", "treatment", "drug", "therapy", "cancer", "doctor"}),
        ("insurance", {"insurance", "medicaid", "medicare", "coverage", "premium"}),
    ],
    "Science": [
        ("climate", {"climate", "warming", "emissions", "carbon"}),
        ("space", {"space", "nasa", "rocket", "moon", "mars", "satellite"}),
        ("environment", {"environment", "wildlife", "species", "pollution", "conservation"}),
        ("research", {"research", "study", "scientists", "journal", "discovery"}),
    ],
}

_EVENT_TYPE_RULES: list[tuple[str, set[str]]] = [
    ("redistricting", {"redistricting", "gerrymander", "district map", "maps"}),
    ("election", {"election", "campaign", "vote", "voting", "poll", "ballot"}),
    ("legal", {"court", "judge", "lawsuit", "sues", "trial", "ruling", "charged", "indictment"}),
    ("regulation_policy", {"regulation", "regulate", "rule", "rules", "bill", "law", "ban", "order", "policy"}),
    ("violence_conflict", {"shooting", "attack", "strike", "war", "ceasefire", "bomb", "killed"}),
    ("markets", {"market", "stocks", "shares", "inflation", "rates", "fed"}),
    ("corporate_results", {"earnings", "profit", "revenue", "quarterly"}),
    ("labor_action", {"strike", "union", "workers", "labor", "wages"}),
    ("public_health", {"outbreak", "vaccine", "disease", "public health"}),
    ("research", {"study", "research", "scientists", "discovery"}),
    ("product_launch", {"launch", "release", "unveils", "announces", "model"}),
]


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


def _comparison_topic(title: str, title_entities: list[str]) -> str:
    tokens = _topic_tokens(title)
    lower_tokens = [token.lower() for token in tokens]
    if "vs" not in lower_tokens and "versus" not in lower_tokens:
        return ""

    split_index = next((index for index, token in enumerate(lower_tokens) if token in {"vs", "versus"}), -1)
    if split_index < 0:
        return ""

    left_tokens = tokens[:split_index]
    right_tokens = tokens[split_index + 1 :]

    left_entities = _clean_topic_tokens(left_tokens)
    right_entities = _clean_topic_tokens(right_tokens)
    left_choice = next((token for token in left_entities if _is_strong_topic_token(token)), "")
    right_choice = next((token for token in right_entities if _is_strong_topic_token(token)), "")

    if left_choice and right_choice:
        return _topic_phrase_from_tokens([left_choice, right_choice])

    if title_entities:
        filtered = [entity for entity in title_entities if not _is_generic_entity_hint(entity)]
        if len(filtered) >= 2:
            return f"{filtered[0]} {filtered[1]}"

    return ""


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

    comparison_topic = _comparison_topic(title, entity_candidates)
    if comparison_topic and not _is_generic_topic(comparison_topic):
        return comparison_topic

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


def _contains_any(text_key: str, tokens: set[str], markers: set[str]) -> bool:
    for marker in markers:
        marker_key = _normalize_topic_key(marker)
        if not marker_key:
            continue
        if " " in marker_key and marker_key in text_key:
            return True
        if marker_key in tokens:
            return True
    return False


def _classification_text(
    title: str,
    content_text: str,
    *,
    keywords: list[str] | None = None,
    entities: list[str] | None = None,
) -> tuple[str, set[str]]:
    values = [
        normalize_whitespace(title),
        normalize_whitespace(content_text[:3000]),
        " ".join(str(item) for item in keywords or []),
        " ".join(str(item) for item in entities or []),
    ]
    text_key = _normalize_topic_key(" ".join(value for value in values if value))
    return text_key, set(text_key.split())


def _classify_primary_topic(text_key: str, tokens: set[str]) -> str:
    scores: dict[str, int] = {topic: 0 for topic in PRIMARY_TOPICS}
    for topic, markers in _PRIMARY_TOPIC_RULES:
        for marker in markers:
            marker_key = _normalize_topic_key(marker)
            if not marker_key:
                continue
            if " " in marker_key:
                scores[topic] += 2 if marker_key in text_key else 0
            elif marker_key in tokens:
                scores[topic] += 1

    ranked = sorted(scores.items(), key=lambda item: (-item[1], PRIMARY_TOPICS.index(item[0])))
    if ranked and ranked[0][1] > 0:
        return ranked[0][0]
    return "U.S." if tokens.intersection({"us", "u", "s", "american", "state", "city", "county"}) else "World"


def _classify_subtopic(primary_topic: str, text_key: str, tokens: set[str]) -> str | None:
    for subtopic, markers in _SUBTOPIC_RULES.get(primary_topic, []):
        if _contains_any(text_key, tokens, markers):
            return subtopic
    return None


def _classify_geography(text_key: str, tokens: set[str], entities: list[str] | None) -> str | None:
    for entity in entities or []:
        entity_key = _normalize_topic_key(entity)
        if entity_key in _US_STATE_TERMS or entity_key in _WORLD_GEO_TERMS:
            return entity_key.replace(" ", "_")

    for state in sorted(_US_STATE_TERMS, key=len, reverse=True):
        if (" " in state and state in text_key) or state in tokens:
            return state.replace(" ", "_")

    for location in sorted(_WORLD_GEO_TERMS, key=len, reverse=True):
        if (" " in location and location in text_key) or location in tokens:
            if location in {"gaza", "israel", "iran", "iraq", "lebanon", "syria", "yemen", "middle east"}:
                return "middle_east"
            if location in {"ukraine", "russia"}:
                return "ukraine_russia"
            if location in {"europe", "eu", "france", "germany", "britain", "united kingdom", "uk"}:
                return "europe"
            if location in {"china", "india", "japan", "taiwan"}:
                return "asia"
            return location.replace(" ", "_")

    if tokens.intersection({"us", "usa", "american"}) or "united states" in text_key:
        return "united_states"
    return None


def _classify_event_type(text_key: str, tokens: set[str]) -> str | None:
    for event_type, markers in _EVENT_TYPE_RULES:
        if _contains_any(text_key, tokens, markers):
            return event_type
    return None


def _key_entities_from_values(
    title: str,
    content_text: str,
    *,
    entities: list[str] | None = None,
    limit: int = 8,
) -> tuple[str, ...]:
    candidates: list[str] = []
    seen: set[str] = set()
    for value in [*(entities or []), *_candidate_subject_entities(title, content_text)]:
        normalized = normalize_whitespace(str(value))
        key = _normalize_topic_key(normalized)
        if not normalized or not key or key in seen or _is_generic_topic(normalized):
            continue
        seen.add(key)
        candidates.append(normalized)
        if len(candidates) >= limit:
            break
    return tuple(candidates)


def classify_topic_from_text(
    title: str,
    content_text: str = "",
    *,
    keywords: list[str] | None = None,
    entities: list[str] | None = None,
) -> TopicClassification:
    text_key, tokens = _classification_text(title, content_text, keywords=keywords, entities=entities)
    primary_topic = _classify_primary_topic(text_key, tokens)
    return TopicClassification(
        primary_topic=primary_topic,
        subtopic=_classify_subtopic(primary_topic, text_key, tokens),
        key_entities=_key_entities_from_values(title, content_text, entities=entities),
        geography=_classify_geography(text_key, tokens, entities),
        event_type=_classify_event_type(text_key, tokens),
    )


def classify_topic_from_article(article: Article) -> TopicClassification:
    source_article = getattr(article, "article", None)
    if source_article is not None:
        return classify_topic_from_article(source_article)
    return classify_topic_from_text(
        getattr(article, "title", "") or "",
        f"{getattr(article, 'publisher', '') or ''} {getattr(article, 'content_text', '') or ''}",
        keywords=list(getattr(article, "keywords", []) or []),
        entities=list(getattr(article, "entities", []) or []),
    )


def apply_topic_classification(article: Article) -> TopicClassification:
    classification = classify_topic_from_article(article)
    article.primary_topic = classification.primary_topic
    article.subtopic = classification.subtopic
    article.key_entities = list(classification.key_entities)
    article.geography = classification.geography
    article.event_type = classification.event_type
    return classification
