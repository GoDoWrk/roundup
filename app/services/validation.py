from __future__ import annotations

from dataclasses import dataclass
import re

from app.db.models import Cluster


REQUIRED_TEXT_FIELDS = ["headline", "summary", "what_changed", "why_it_matters"]
DETAIL_FIELDS = ["summary", "what_changed", "why_it_matters"]
PLACEHOLDER_SNIPPETS = {
    "pending",
    "tbd",
    "n/a",
    "no summary available",
    "no headline available",
    "no impact statement available",
    "no change summary available",
}


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]

    @property
    def error(self) -> str | None:
        return "; ".join(self.errors) if self.errors else None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _word_count(text: str) -> int:
    return len(_tokenize(text))


def _is_placeholder_like(text: str) -> bool:
    normalized = " ".join(_tokenize(text))
    if not normalized:
        return True
    return any(snippet in normalized for snippet in PLACEHOLDER_SNIPPETS)


def _is_repetitive(text: str) -> bool:
    tokens = _tokenize(text)
    if len(tokens) < 6:
        return False
    unique_ratio = len(set(tokens)) / len(tokens)
    return unique_ratio < 0.45


def validate_cluster_record(
    cluster: Cluster,
    *,
    source_count: int,
    min_sources: int,
    min_headline_words: int,
    min_detail_words: int,
) -> ValidationResult:
    errors: list[str] = []

    for field_name in REQUIRED_TEXT_FIELDS:
        value = getattr(cluster, field_name, "")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name} must be non-empty")
            continue

        text = value.strip()
        minimum_words = min_detail_words if field_name in DETAIL_FIELDS else min_headline_words
        if _word_count(text) < minimum_words:
            errors.append(f"{field_name} is too short")
        if _is_placeholder_like(text):
            errors.append(f"{field_name} looks like placeholder text")
        if _is_repetitive(text):
            errors.append(f"{field_name} is overly repetitive")

    normalized_fields = [" ".join(_tokenize(getattr(cluster, name, ""))) for name in DETAIL_FIELDS]
    non_empty_fields = [field for field in normalized_fields if field]
    if len(set(non_empty_fields)) < len(non_empty_fields):
        errors.append("detail fields must not repeat the same sentence")

    if source_count < min_sources:
        errors.append(f"cluster must have at least {min_sources} sources")

    return ValidationResult(is_valid=not errors, errors=errors)
