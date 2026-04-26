from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import clusters as cluster_routes
from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle


def _article(
    idx: int,
    cluster_id: str,
    now: datetime,
    publisher: str,
    raw_payload: dict | None = None,
    image_url: str | None = None,
) -> Article:
    return Article(
        external_id=None,
        title=f"Transit update {idx}",
        url=f"https://example.com/{cluster_id}/{idx}",
        canonical_url=f"https://example.com/{cluster_id}/{idx}",
        publisher=publisher,
        published_at=now - timedelta(hours=idx),
        content_text="Body",
        image_url=image_url,
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


def _add_visible_cluster(db_session: Session, cluster_id: str, now: datetime, *, with_images: bool) -> Cluster:
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
    return cluster


def _assert_enriched_story_contract(
    payload: dict,
    *,
    image_expected: bool,
    developing_expected: bool = True,
    related_cluster_ids: list[str] | None = None,
) -> None:
    assert ENRICHED_STORY_FIELDS <= set(payload.keys())
    assert payload["source_count"] == 3
    assert len(payload["sources"]) == 3
    assert payload["key_facts"]
    assert any("3 sources" in fact for fact in payload["key_facts"])
    assert payload["timeline_events"] == payload["timeline"]
    assert len(payload["timeline_events"]) == 3
    assert isinstance(payload["topic"], str)
    assert payload["topic"]
    assert payload["region"] is None
    assert payload["story_type"] == "general"
    assert payload["is_developing"] is developing_expected
    assert payload["is_breaking"] is False
    assert payload["confidence_score"] == payload["score"]
    assert payload["related_cluster_ids"] == (related_cluster_ids or [])

    if image_expected:
        assert payload["primary_image_url"] == "https://images.example.com/transit-enclosure.jpg"
        assert payload["thumbnail_urls"] == [
            "https://images.example.com/transit-enclosure.jpg",
            "https://images.example.com/transit-lead.jpg",
        ]
        source_images = {source["image_url"] for source in payload["sources"]}
        assert "https://images.example.com/transit-enclosure.jpg" in source_images
        assert "https://images.example.com/transit-lead.jpg" in source_images
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
    assert payload["endpoints"]["homepage_clusters"] == "/api/clusters/homepage"
    assert payload["endpoints"]["search"] == "/api/search?q=..."
    assert payload["endpoints"]["sources"] == "/api/sources"
    assert payload["endpoints"]["debug_clusters"] == "/debug/clusters"
    assert payload["endpoints"]["metrics"] == "/metrics"


def test_homepage_clusters_sections_promoted_and_candidate_stories(
    client,
    db_session: Session,
    monkeypatch,
) -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="token",
        cluster_min_sources_for_api=2,
        cluster_min_sources_for_top_stories=2,
        cluster_min_sources_for_developing_stories=2,
        cluster_homepage_top_limit=1,
        cluster_homepage_developing_limit=2,
        cluster_homepage_just_in_limit=4,
        cluster_show_just_in_single_source=True,
    )
    monkeypatch.setattr(cluster_routes, "get_settings", lambda: settings)

    now = datetime.now(timezone.utc)
    top = _add_visible_cluster(db_session, "homepage-top", now - timedelta(hours=1), with_images=False)
    top.score = 0.95
    top.headline = "Top Confirmed Transit Story"

    developing = _cluster("homepage-developing", now)
    developing.score = 0.72
    db_session.add(developing)
    db_session.flush()
    for idx, publisher in enumerate(["Daily One", "Daily Two"], start=1):
        article = _article(idx, developing.id, now, publisher)
        article.dedupe_hash = f"{developing.id}-{idx}"
        article.url = f"https://example.com/{developing.id}/{idx}"
        article.canonical_url = article.url
        db_session.add(article)
        db_session.flush()
        db_session.add(ClusterArticle(cluster_id=developing.id, article_id=article.id, similarity_score=0.72, heuristic_breakdown={}))

    candidate = _cluster("homepage-candidate", now - timedelta(minutes=20))
    candidate.status = "hidden"
    candidate.score = 1.0
    candidate.headline = "Single Source Candidate Story"
    db_session.add(candidate)
    db_session.flush()
    article = _article(1, candidate.id, now, "Candidate Wire")
    article.dedupe_hash = f"{candidate.id}-1"
    article.url = f"https://example.com/{candidate.id}/1"
    article.canonical_url = article.url
    db_session.add(article)
    db_session.flush()
    db_session.add(ClusterArticle(cluster_id=candidate.id, article_id=article.id, similarity_score=1.0, heuristic_breakdown={}))
    db_session.commit()

    response = client.get("/api/clusters/homepage")

    assert response.status_code == 200
    payload = response.json()
    assert [item["cluster_id"] for item in payload["sections"]["top_stories"]] == ["homepage-top"]
    assert [item["cluster_id"] for item in payload["sections"]["developing_stories"]] == ["homepage-developing"]
    assert [item["cluster_id"] for item in payload["sections"]["just_in"]] == ["homepage-candidate"]
    assert payload["sections"]["just_in"][0]["visibility"] == "candidate"
    assert payload["sections"]["just_in"][0]["visibility_label"] == "Single source"
    assert payload["sections"]["just_in"][0]["is_single_source"] is True
    assert payload["status"]["visible_clusters"] == 2
    assert payload["status"]["candidate_clusters"] == 1


def test_api_clusters_list_and_detail_return_structured_payloads(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    api_cluster = _add_visible_cluster(db_session, "api-cluster", now, with_images=True)
    _add_visible_cluster(db_session, "no-image-cluster", now - timedelta(days=2), with_images=False)
    api_cluster.related_cluster_ids = ["no-image-cluster"]

    db_session.commit()

    list_response = client.get("/api/clusters")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert {"total", "limit", "offset", "items"} <= set(list_payload.keys())

    item = next(row for row in list_payload["items"] if row["cluster_id"] == "api-cluster")
    _assert_enriched_story_contract(item, image_expected=True, related_cluster_ids=["no-image-cluster"])

    detail_response = client.get("/api/clusters/api-cluster")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["cluster_id"] == "api-cluster"
    _assert_enriched_story_contract(detail_payload, image_expected=True, related_cluster_ids=["no-image-cluster"])

    no_image_response = client.get("/api/clusters/no-image-cluster")
    assert no_image_response.status_code == 200
    no_image_payload = no_image_response.json()
    assert no_image_payload["cluster_id"] == "no-image-cluster"
    _assert_enriched_story_contract(no_image_payload, image_expected=False, developing_expected=False)


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
    _assert_enriched_story_contract(detail_response.json(), image_expected=False)


def test_api_search_returns_cluster_results_for_known_headline(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    _add_visible_cluster(db_session, "search-transit", now, with_images=True)
    db_session.commit()

    response = client.get("/api/search?q=transit")
    assert response.status_code == 200
    payload = response.json()

    assert payload["query"] == "transit"
    assert payload["total"] >= 1
    assert payload["counts"]["all"] == payload["total"]
    assert payload["counts"]["clusters"] >= 1

    cluster_result = next(item for item in payload["items"] if item["cluster_id"] == "search-transit" and item["type"] == "cluster")
    assert cluster_result["title"] == "City Council Approves Transit Plan"
    assert cluster_result["thumbnail_url"] == "https://images.example.com/transit-enclosure.jpg"
    assert cluster_result["matched_field"] in {"headline", "summary", "article_title"}
    assert cluster_result["source_count"] == 3
    assert cluster_result["update_count"] == 3


def test_api_search_returns_update_results_for_change_and_impact_fields(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    cluster = _add_visible_cluster(db_session, "search-update", now, with_images=False)
    cluster.what_changed = "Funding negotiations moved into a final public vote."
    cluster.why_it_matters = "The decision affects commuters who depend on late-night service."
    db_session.commit()

    response = client.get("/api/search?q=funding")
    assert response.status_code == 200
    payload = response.json()

    update_result = next(item for item in payload["items"] if item["cluster_id"] == "search-update" and item["type"] == "update")
    assert update_result["matched_field"] == "what_changed"
    assert "Funding negotiations" in update_result["snippet"]
    assert payload["counts"]["updates"] >= 1


def test_api_search_returns_source_results_for_publisher(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    _add_visible_cluster(db_session, "search-source", now, with_images=False)
    article = db_session.scalars(select(Article).where(Article.dedupe_hash == "search-source-1")).one()
    article.publisher = "Reuters"
    db_session.commit()

    response = client.get("/api/search?q=Reuters")
    assert response.status_code == 200
    payload = response.json()

    source_result = next(item for item in payload["items"] if item["type"] == "source")
    assert source_result["cluster_id"] == "search-source"
    assert source_result["source_name"] == "Reuters"
    assert source_result["article_url"] == "https://example.com/search-source/1"
    assert source_result["published_at"] is not None
    assert source_result["matched_field"] == "publisher"
    assert payload["counts"]["sources"] >= 1


def test_api_search_handles_empty_query(client) -> None:
    response = client.get("/api/search?q=%20%20")
    assert response.status_code == 200
    payload = response.json()

    assert payload == {
        "query": "",
        "total": 0,
        "limit": 50,
        "counts": {"all": 0, "clusters": 0, "updates": 0, "sources": 0},
        "items": [],
    }


def test_api_search_uses_public_cluster_visibility_filters(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    visible = _add_visible_cluster(db_session, "filtered-visible", now, with_images=False)
    visible.headline = "Filtered Visibility Transit Story"

    hidden = _cluster("filtered-hidden", now)
    hidden.headline = "Filtered Hidden Transit Story"
    hidden.status = "hidden"
    db_session.add(hidden)
    db_session.flush()
    for idx, publisher in enumerate(["Hidden One", "Hidden Two", "Hidden Three"], start=1):
        article = _article(idx, hidden.id, now, publisher)
        db_session.add(article)
        db_session.flush()
        db_session.add(ClusterArticle(cluster_id=hidden.id, article_id=article.id, similarity_score=0.7, heuristic_breakdown={}))

    small = _cluster("filtered-small", now)
    small.headline = "Filtered Small Transit Story"
    db_session.add(small)
    db_session.flush()
    article = _article(1, small.id, now, "Small One")
    db_session.add(article)
    db_session.flush()
    db_session.add(ClusterArticle(cluster_id=small.id, article_id=article.id, similarity_score=0.7, heuristic_breakdown={}))

    invalid = _cluster("filtered-invalid", now)
    invalid.headline = "Filtered Invalid Transit Story"
    invalid.validation_error = "manual block"
    db_session.add(invalid)
    db_session.flush()
    for idx, publisher in enumerate(["Invalid One", "Invalid Two", "Invalid Three"], start=1):
        article = _article(idx, invalid.id, now, publisher)
        article.dedupe_hash = f"{invalid.id}-{idx}"
        article.url = f"https://example.com/{invalid.id}/{idx}"
        article.canonical_url = article.url
        db_session.add(article)
        db_session.flush()
        db_session.add(ClusterArticle(cluster_id=invalid.id, article_id=article.id, similarity_score=0.7, heuristic_breakdown={}))

    db_session.commit()

    response = client.get("/api/search?q=Filtered")
    assert response.status_code == 200
    cluster_ids = {item["cluster_id"] for item in response.json()["items"]}

    assert "filtered-visible" in cluster_ids
    assert "filtered-hidden" not in cluster_ids
    assert "filtered-small" not in cluster_ids
    assert "filtered-invalid" not in cluster_ids
