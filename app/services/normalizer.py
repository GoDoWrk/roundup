from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
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

IMAGE_EXTENSIONS = {".apng", ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


@dataclass(frozen=True)
class NormalizedArticle:
    external_id: str
    title: str
    url: str
    canonical_url: str
    publisher: str
    published_at: datetime
    content_text: str
    image_url: str | None
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


def is_valid_image_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    candidate = normalize_whitespace(value)
    if not candidate:
        return False
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _append_candidate(candidates: list[str], value: object) -> None:
    if is_valid_image_url(value):
        candidates.append(normalize_whitespace(str(value)))


def _dedupe_image_urls(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for candidate in candidates:
        parsed = urlparse(candidate)
        normalized = urlunparse(parsed._replace(fragment=""))
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(normalized)
    return urls


def _mime_is_image(value: object) -> bool:
    return isinstance(value, str) and value.lower().split(";", 1)[0].strip().startswith("image/")


def _url_path_looks_like_image(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(normalize_whitespace(value))
    path = parsed.path.lower()
    return any(path.endswith(extension) for extension in IMAGE_EXTENSIONS)


def _enclosure_may_be_image(enclosure: dict) -> bool:
    mime_type = enclosure.get("mime_type") or enclosure.get("type")
    url = enclosure.get("url") or enclosure.get("href")
    if _mime_is_image(mime_type):
        return True
    if mime_type in {None, ""}:
        return _url_path_looks_like_image(url)
    if isinstance(mime_type, str) and mime_type.lower().split(";", 1)[0].strip() == "application/octet-stream":
        return _url_path_looks_like_image(url)
    return False


def _append_nested_metadata_candidates(candidates: list[str], entry: dict) -> None:
    metadata_keys = ("metadata", "meta", "article_metadata", "open_graph", "opengraph", "twitter")
    image_keys = ("image", "image_url", "thumbnail", "thumbnail_url", "lead_image_url", "og:image", "twitter:image")

    for key in metadata_keys:
        nested = entry.get(key)
        if not isinstance(nested, dict):
            continue
        for image_key in image_keys:
            value = nested.get(image_key)
            if isinstance(value, dict):
                _append_candidate(candidates, value.get("url") or value.get("href") or value.get("src"))
            else:
                _append_candidate(candidates, value)


def _append_media_candidates(candidates: list[str], entry: dict) -> None:
    thumbnail_value = entry.get("media_thumbnail")
    thumbnail_items = thumbnail_value if isinstance(thumbnail_value, list) else [thumbnail_value]
    for item in thumbnail_items:
        if isinstance(item, dict):
            _append_candidate(candidates, item.get("url") or item.get("href") or item.get("src"))

    media_value = entry.get("media_content")
    media_items = media_value if isinstance(media_value, list) else [media_value]
    for item in media_items:
        if not isinstance(item, dict):
            continue
        medium = str(item.get("medium") or "").lower()
        mime_type = item.get("type") or item.get("mime_type")
        if medium == "image" or _mime_is_image(mime_type):
            _append_candidate(candidates, item.get("url") or item.get("href") or item.get("src"))

    raw_links = entry.get("links") or []
    links = raw_links if isinstance(raw_links, list) else [raw_links]
    for link in links:
        if not isinstance(link, dict):
            continue
        rel = str(link.get("rel") or "").lower()
        mime_type = link.get("type")
        if rel in {"enclosure", "thumbnail", "image"} or _mime_is_image(mime_type):
            _append_candidate(candidates, link.get("href") or link.get("url"))


def _append_enclosure_candidates(candidates: list[str], entry: dict) -> None:
    raw_enclosures = entry.get("enclosures") or entry.get("enclosure") or []
    enclosures = raw_enclosures if isinstance(raw_enclosures, list) else [raw_enclosures]
    for enclosure in enclosures:
        if not isinstance(enclosure, dict):
            continue
        if _enclosure_may_be_image(enclosure):
            _append_candidate(candidates, enclosure.get("url") or enclosure.get("href"))


def _append_html_metadata_candidates(candidates: list[str], html: str) -> None:
    if not html:
        return

    meta_pattern = re.compile(r"<meta\b(?P<attrs>[^>]*?)>", re.IGNORECASE)
    attr_pattern = re.compile(r"([A-Za-z_:.-]+)\s*=\s*(['\"])(.*?)\2", re.IGNORECASE | re.DOTALL)
    desired = {"og:image", "twitter:image", "twitter:image:src"}
    fallback_images: list[str] = []

    for match in meta_pattern.finditer(html):
        attrs = {name.lower(): unescape(value.strip()) for name, _, value in attr_pattern.findall(match.group("attrs"))}
        name = attrs.get("property") or attrs.get("name")
        if name and name.lower() in desired:
            _append_candidate(candidates, attrs.get("content"))

    img_pattern = re.compile(r"<img\b(?P<attrs>[^>]*?)>", re.IGNORECASE)
    for match in img_pattern.finditer(html):
        attrs = {name.lower(): unescape(value.strip()) for name, _, value in attr_pattern.findall(match.group("attrs"))}
        src = attrs.get("src")
        if is_valid_image_url(src):
            fallback_images.append(normalize_whitespace(str(src)))

    candidates.extend(fallback_images)


def extract_image_url(entry: dict, content: str = "") -> str | None:
    try:
        candidates: list[str] = []
        for key in ("image_url", "thumbnail_url", "lead_image_url"):
            _append_candidate(candidates, entry.get(key))

        image_value = entry.get("image")
        if isinstance(image_value, dict):
            _append_candidate(candidates, image_value.get("url") or image_value.get("href") or image_value.get("src"))
        else:
            _append_candidate(candidates, image_value)

        _append_nested_metadata_candidates(candidates, entry)
        _append_media_candidates(candidates, entry)
        _append_enclosure_candidates(candidates, entry)
        _append_html_metadata_candidates(candidates, content)

        urls = _dedupe_image_urls(candidates)
        return urls[0] if urls else None
    except Exception:
        return None


def normalize_miniflux_entry(entry: dict) -> NormalizedArticle:
    title = normalize_whitespace(str(entry.get("title") or "Untitled article"))
    url = normalize_whitespace(str(entry.get("url") or ""))
    canonical_url = canonicalize_url(url)

    content = normalize_whitespace(str(entry.get("content") or ""))
    image_url = extract_image_url(entry, content)
    publisher = normalize_whitespace(
        str((entry.get("feed") or {}).get("title") or entry.get("author") or "unknown")
    )
    published_at = parse_published_at(entry.get("published_at"))

    normalized_title_value = normalize_title(title)
    keyword_text = f"{title} {content[:2000]}"
    keywords = extract_keywords(keyword_text)
    entities = extract_entities(keyword_text)
    topic = derive_topic_from_text(title, content, keywords=keywords, entities=entities)

    dedupe_hash = build_dedupe_hash(canonical_url, normalized_title_value, published_at)

    return NormalizedArticle(
        external_id=str(entry.get("id") or ""),
        title=title,
        url=url,
        canonical_url=canonical_url,
        publisher=publisher or "unknown",
        published_at=published_at,
        content_text=content[:10000],
        image_url=image_url,
        raw_payload=entry,
        normalized_title=normalized_title_value,
        keywords=keywords,
        entities=entities,
        topic=topic,
        dedupe_hash=dedupe_hash,
    )
