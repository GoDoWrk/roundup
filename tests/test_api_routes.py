from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle


def _article(idx: int, cluster_id: str, now: datetime, publisher: str, image_url: str | None = None) -> Article:
    return Article(
        external_id=None,
        title=f"Transit update {idx}",
        url=f"https://example.com/{cluster_id}/{idx}",
        canonical_url=f"https://example.com/{cluster_id}/{idx}",
        publisher=publisher,
        published_at=now - timedelta(hours=idx),
        content_text="Body",
        image_url=image_url,
        raw_payload={"id": idx},
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
    cluster = _cluster("api-cluster", now)
    db_session.add(cluster)
    db_session.flush()

    for idx, publisher in enumerate(["Daily One", "Daily Two", "Daily Three"], start=1):
        article = _article(
            idx,
            cluster.id,
            now,
            publisher,
            image_url=f"https://cdn.example.com/{cluster.id}/{idx}.jpg" if idx != 2 else None,
        )
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

    db_session.commit()

    list_response = client.get("/api/clusters")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert {"total", "limit", "offset", "items"} <= set(list_payload.keys())

    item = next(row for row in list_payload["items"] if row["cluster_id"] == "api-cluster")
    assert {
        "headline",
        "summary",
        "what_changed",
        "why_it_matters",
        "primary_image_url",
        "thumbnail_urls",
        "timeline",
        "sources",
        "score",
        "status",
    } <= set(item.keys())
    assert "topic" in item
    assert item["primary_image_url"] == "https://cdn.example.com/api-cluster/1.jpg"
    assert item["thumbnail_urls"] == [
        "https://cdn.example.com/api-cluster/1.jpg",
        "https://cdn.example.com/api-cluster/3.jpg",
    ]
    assert len(item["sources"]) == 3
    assert item["sources"][0]["image_url"] == "https://cdn.example.com/api-cluster/1.jpg"

    detail_response = client.get("/api/clusters/api-cluster")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["cluster_id"] == "api-cluster"
    assert "topic" in detail_payload
    assert detail_payload["primary_image_url"] == "https://cdn.example.com/api-cluster/1.jpg"
    assert detail_payload["thumbnail_urls"] == [
        "https://cdn.example.com/api-cluster/1.jpg",
        "https://cdn.example.com/api-cluster/3.jpg",
    ]
    assert len(detail_payload["sources"]) == 3
    assert isinstance(detail_payload["timeline"], list)


def test_api_clusters_detail_keeps_low_score_cluster_public_when_it_is_valid(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster("low-score-cluster", now)
    cluster.score = 0.21
    db_session.add(cluster)
    db_session.flush()

    for idx, publisher in enumerate(["Daily One", "Daily Two", "Daily Three"], start=1):
        article = _article(idx, cluster.id, now, publisher)
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=cluster.id,
                article_id=article.id,
                similarity_score=0.21,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.21},
            )
        )

    db_session.commit()

    list_response = client.get("/api/clusters")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert any(row["cluster_id"] == "low-score-cluster" for row in list_payload["items"])

    detail_response = client.get("/api/clusters/low-score-cluster")
    assert detail_response.status_code == 200
