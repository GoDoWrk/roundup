from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Cluster
from app.services.validation import validate_cluster_record


def _cluster(**overrides: object) -> Cluster:
    base: dict[str, object] = {
        "id": "cluster-1",
        "headline": "City Council Approves Transit Expansion Plan",
        "summary": "Multiple outlets report the transit expansion plan and confirm funding steps and implementation timelines.",
        "what_changed": "Coverage expanded from an initial city statement to broader reporting with budget and route details.",
        "why_it_matters": "The project affects commute costs and service access, with sustained updates showing ongoing public impact.",
        "first_seen": datetime.now(timezone.utc),
        "last_updated": datetime.now(timezone.utc),
        "score": 0.72,
        "status": "active",
        "normalized_headline": "city council approves transit expansion plan",
        "keywords": ["city", "council", "transit", "expansion"],
        "entities": ["City Council"],
    }
    base.update(overrides)
    return Cluster(**base)


def test_validation_rejects_missing_required_text() -> None:
    cluster = _cluster(summary="")
    result = validate_cluster_record(
        cluster,
        source_count=3,
        min_sources=3,
        min_headline_words=3,
        min_detail_words=8,
    )

    assert not result.is_valid
    assert result.error is not None
    assert "summary must be non-empty" in result.error


def test_validation_rejects_weak_or_repetitive_text() -> None:
    cluster = _cluster(
        summary="pending pending pending pending pending pending pending pending",
        what_changed="update update update update update update update update",
    )
    result = validate_cluster_record(
        cluster,
        source_count=3,
        min_sources=3,
        min_headline_words=3,
        min_detail_words=8,
    )

    assert not result.is_valid
    assert result.error is not None
    assert "placeholder" in result.error or "repetitive" in result.error


def test_validation_rejects_cluster_when_source_count_below_threshold() -> None:
    cluster = _cluster()
    result = validate_cluster_record(
        cluster,
        source_count=2,
        min_sources=3,
        min_headline_words=3,
        min_detail_words=8,
    )

    assert not result.is_valid
    assert result.error is not None
    assert "at least 3 sources" in result.error
