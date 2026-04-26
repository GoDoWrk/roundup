from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle


def _article(
    idx: int,
    cluster_id: str,
    now: datetime,
    publisher: str,
    raw_payload: dict | None = None,
) -> Article:
    return Article(
        external_id=None,
        title=f"Transit update {idx}",
        url=f"https://example.com/{cluster_id}/{idx}",
        canonical_url=f"https://example.com/{cluster_id}/{idx}",
        publisher=publisher,
        published_at=now - timedelta(hours=idx),
        content_text="Body",
        raw_payload=raw_payload or {"id": idx},
        normalized_title=f"transit update {idx}",
        keywords=["transit", "update", "city"],
        entities=["City Council"],
        dedupe_hash=f"{cluster_id}-{idx}",
    )


def _cluster(cluster_id: str, now: datetime) -> Cluster:
    return Cluster(
        id=cluster_id,
        headline="City Council Approves Transit Plan",
        summary="Three outlets are covering the transit plan update with consistent facts and newly released details.",
        what_changed="Coverage moved from the initial announcement to broader reporting on funding and route impacts.",
        why_it_matters="The change affects transit availability and costs, and sustained updates indicate continuing relevance.",
        first_seen=now - timedelta(hours=4),
        last_updated=now,
        score=0.74,
        status="active",
        normalized_headline="city council approves transit plan",
        keywords=["city", "council", "transit", "plan"],
        entities=["City Council"],
        validation_error=None,
    )


ENRICHED_STORY_FIELDS = {
    "headline",
    "summary",
    "what_changed",
    "why_it_matters",
    "key_facts",
    "timeline",
    "timeline_events",
    "sources",
    "source_count",
    "primary_image_url",
    "thumbnail_urls",
    "topic",
    "region",
    "story_type",
    "first_seen",
    "last_updated",
    "is_developing",
    "is_breaking",
    "confidence_score",
    "related_cluster_ids",
    "score",
    "status",
}


def _add_visible_cluster(db_session: Session, cluster_id: str, now: datetime, *, with_images: bool) -> None:
    cluster = _cluster(cluster_id, now)
    db_session.add(cluster)
    db_session.flush()

    for idx, publisher in enumerate(["Daily One", "Daily Two", "Daily Three"], start=1):
        raw_payload = {"id": idx}
        if with_images and idx == 2:
            raw_payload["enclosures"] = [
                {
                    "mime_type": "image/jpeg",
                    "url": "https://images.example.com/transit-enclosure.jpg",
                }
            ]
        if with_images and idx == 3:
            raw_payload["image_url"] = "https://images.example.com/transit-lead.jpg"

        article = _article(idx, cluster.id, now, publisher, raw_payload)
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=cluster.id,
                article_id=article.id,
                similarity_score=0.72,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.72},
            )
        )


def _assert_enriched_story_contract(payload: dict, *, image_expected: bool, developing_expected: bool = True) -> None:
    assert ENRICHED_STORY_FIELDS <= set(payload.keys())
    assert payload["source_count"] == 3
    assert len(payload["sources"]) == 3
    assert payload["key_facts"] == []
    assert payload["timeline_events"] == payload["timeline"]
    assert len(payload["timeline_events"]) == 3
    assert payload["topic"] == "city"
    assert payload["region"] is None
    assert payload["story_type"] == "general"
    assert payload["is_developing"] is developing_expected
    assert payload["is_breaking"] is False
    assert payload["confidence_score"] == payload["score"]
    assert payload["related_cluster_ids"] == []

    if image_expected:
        assert payload["primary_image_url"] == "https://images.example.com/transit-lead.jpg"
        assert payload["thumbnail_urls"] == [
            "https://images.example.com/transit-lead.jpg",
            "https://images.example.com/transit-enclosure.jpg",
        ]
    else:
        assert payload["primary_image_url"] is None
        assert payload["thumbnail_urls"] == []


def test_root_index_lists_debug_endpoints(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()

    assert payload["docs_url"] == "/docs"
    assert payload["endpoints"]["health"] == "/health"
    assert payload["endpoints"]["clusters"] == "/api/clusters"
    assert payload["endpoints"]["debug_clusters"] == "/debug/clusters"
    assert payload["endpoints"]["metrics"] == "/metrics"


def test_api_clusters_list_and_detail_return_structured_payloads(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    _add_visible_cluster(db_session, "api-cluster", now, with_images=True)
    _add_visible_cluster(db_session, "no-image-cluster", now - timedelta(days=2), with_images=False)

    db_session.commit()

    list_response = client.get("/api/clusters")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert {"total", "limit", "offset", "items"} <= set(list_payload.keys())

    item = next(row for row in list_payload["items"] if row["cluster_id"] == "api-cluster")
    _assert_enriched_story_contract(item, image_expected=True)

    detail_response = client.get("/api/clusters/api-cluster")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["cluster_id"] == "api-cluster"
    _assert_enriched_story_contract(detail_payload, image_expected=True)

    no_image_response = client.get("/api/clusters/no-image-cluster")
    assert no_image_response.status_code == 200
    no_image_payload = no_image_response.json()
    assert no_image_payload["cluster_id"] == "no-image-cluster"
    _assert_enriched_story_contract(no_image_payload, image_expected=False, developing_expected=False)
