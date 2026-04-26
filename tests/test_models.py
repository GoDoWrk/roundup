from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.cluster import SourceReference, StoryCluster, TimelineEvent


def _valid_story_cluster() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "cluster_id": "c1",
        "headline": "Headline",
        "summary": "Summary",
        "what_changed": "Change",
        "why_it_matters": "Impact",
        "key_facts": [],
        "timeline": [
            {
                "timestamp": now,
                "event": "Update",
                "source_url": "https://example.com/a",
                "source_title": "A",
            }
        ],
        "timeline_events": [
            {
                "timestamp": now,
                "event": "Update",
                "source_url": "https://example.com/a",
                "source_title": "A",
            }
        ],
        "sources": [
            {
                "article_id": 1,
                "title": "A",
                "url": "https://example.com/a",
                "publisher": "Example",
                "published_at": now,
                "image_url": "https://cdn.example.com/a.jpg",
            }
        ],
        "primary_image_url": "https://cdn.example.com/a.jpg",
        "thumbnail_urls": ["https://cdn.example.com/a.jpg"],
        "source_count": 1,
        "topic": "Transit",
        "region": None,
        "story_type": "general",
        "first_seen": now,
        "last_updated": now,
        "is_developing": True,
        "is_breaking": False,
        "confidence_score": 0.7,
        "related_cluster_ids": [],
        "score": 0.7,
        "status": "active",
    }


def test_story_cluster_rejects_empty_required_text_fields() -> None:
    payload = _valid_story_cluster()
    payload["summary"] = ""
    with pytest.raises(ValidationError):
        StoryCluster(**payload)


def test_story_cluster_accepts_valid_payload() -> None:
    payload = _valid_story_cluster()
    model = StoryCluster(**payload)
    assert model.cluster_id == "c1"
    assert model.summary == "Summary"
    assert model.primary_image_url == "https://cdn.example.com/a.jpg"
    assert model.timeline_events == model.timeline
    assert model.source_count == 1
