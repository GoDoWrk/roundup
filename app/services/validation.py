from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Cluster


REQUIRED_TEXT_FIELDS = ["headline", "summary", "what_changed", "why_it_matters"]


@dataclass
class ValidationResult:
    is_valid: bool
    error: str | None = None


def validate_cluster_record(cluster: Cluster) -> ValidationResult:
    for field_name in REQUIRED_TEXT_FIELDS:
        value = getattr(cluster, field_name, "")
        if not isinstance(value, str) or not value.strip():
            return ValidationResult(False, f"{field_name} must be non-empty")
    return ValidationResult(True, None)
