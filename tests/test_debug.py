from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import Article, Cluster, ClusterArticle


def _article(idx: int, cluster_id: str, now: datetime, publisher: str) -> Article:
    return Article(
        external_id=None,
        title=f"Story update {idx}",
        url=f"https://example.com/{cluster_id}/{idx}",
        canonical_url=f"https://example.com/{cluster_id}/{idx}",
        publisher=publisher,
        published_at=now - timedelta(hours=idx),
        content_text="Body",
        raw_payload={"id": idx},
        normalized_title=f"story update {idx}",
        keywords=["story", "update", "policy"],
        entities=["City Council"],
        dedupe_hash=f"{cluster_id}-{idx}",
    )


def _cluster(cluster_id: str, now: datetime, validation_error: str | None = None) -> Cluster:
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
        validation_error=validation_error,
    )


def test_debug_clusters_includes_explainability_object(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster("debug-cluster", now)
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
                similarity_score=0.7,
                heuristic_breakdown={
                    "decision": "attach_existing_cluster",
                    "selected_score": 0.7,
                    "components": {
                        "title_similarity": 0.8,
                        "entity_jaccard": 0.7,
                        "keyword_jaccard": 0.6,
                        "time_proximity": 0.9,
                    },
                    "thresholds_met": {
                        "signal_gate_passed": True,
                        "title_signal_met": True,
                        "entity_overlap_met": True,
                        "keyword_overlap_met": True,
                    },
                },
            )
        )

    db_session.commit()

    response = client.get("/debug/clusters")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1

    item = next(entry for entry in payload["items"] if entry["cluster_id"] == "debug-cluster")
    explanation = item["debug_explanation"]
    assert explanation["grouping_reason"]
    assert "thresholds" in explanation
    assert "threshold_results" in explanation
    assert "score_breakdown" in explanation
    assert explanation["top_shared_entities"]
    assert explanation["decision_counts"]


def test_api_clusters_filters_out_clusters_below_min_source_count(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    small_cluster = _cluster("small-cluster", now)
    db_session.add(small_cluster)
    db_session.flush()

    for idx in range(2):
        article = _article(idx + 1, small_cluster.id, now, f"Publisher {idx}")
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=small_cluster.id,
                article_id=article.id,
                similarity_score=0.8,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.8},
            )
        )

    db_session.commit()

    response = client.get("/api/clusters")
    assert response.status_code == 200
    payload = response.json()
    assert all(item["cluster_id"] != "small-cluster" for item in payload["items"])
