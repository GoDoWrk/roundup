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
                        "semantic_score": 0.73,
                        "time_proximity": 0.9,
                    },
                    "thresholds_met": {
                        "signal_gate_passed": True,
                        "title_signal_met": True,
                        "entity_overlap_met": True,
                        "keyword_overlap_met": True,
                    },
                    "signal_reasons": ["strong_title_similarity", "meaningful_entity_overlap"],
                    "candidate_diagnostics": [
                        {
                            "article_headline": article.title,
                            "candidate_cluster_headline": cluster.headline,
                            "article_primary_topic": "U.S.",
                            "article_subtopic": None,
                            "cluster_primary_topic": "U.S.",
                            "cluster_subtopic": None,
                            "shared_entities": ["city council"],
                            "conflicting_entities": [],
                            "similarity_score": 0.7,
                            "final_decision": "attach",
                            "rejection_reason": None,
                        }
                    ],
                    "warnings": [],
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
    assert "topic" in item
    assert "primary_topic" in item
    assert "subtopic" in item
    assert "key_entities" in item
    assert "geography" in item
    assert "event_type" in item
    assert "visibility_threshold" in item
    assert "promotion_eligible" in item
    assert "promoted_at" in item
    assert "previous_status" in item
    assert "promotion_reason" in item
    assert "promotion_explanation" in item
    assert "promotion_blockers" in item
    assert explanation["grouping_reason"]
    assert "thresholds" in explanation
    assert explanation["thresholds"]["primary_entity_overlap_required"] is True
    assert "threshold_results" in explanation
    assert "score_breakdown" in explanation
    assert explanation["score_breakdown"]["score_formula"]
    assert explanation["score_breakdown"]["semantic_formula"]
    assert "average_semantic_score" in explanation["score_breakdown"]
    assert explanation["top_shared_entities"]
    assert explanation["decision_counts"]
    assert explanation["recent_join_decisions"]
    assert "source_quality_summary" in explanation
    assert "content_class_summary" in explanation
    assert "warnings" in explanation
    join = explanation["recent_join_decisions"][0]
    assert "semantic_score" in join
    assert "signal_reasons" in join
    assert "matched_features" in join
    assert "ignored_features" in join
    assert "location_overlap" in join
    assert "source_match" in join
    assert "source_quality_reasons" in join
    assert "source_trust" in join
    assert "article_content_class" in join
    assert "cluster_content_class" in join
    assert "membership_rejection_status" in join
    assert "subtopic_match" in join
    assert "subtopic_conflict" in join
    assert "geography_conflict" in join
    assert "event_type_conflict" in join
    assert "candidate_diagnostics" in join
    assert join["candidate_diagnostics"][0]["final_decision"] == "attach"


def test_debug_topic_lanes_returns_counts_and_hidden_reasons(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster("lane-hidden-cluster", now)
    cluster.status = "hidden"
    cluster.primary_topic = "Politics"
    cluster.subtopic = "courts"
    cluster.promotion_reason = "source_count_below_threshold"
    db_session.add(cluster)
    db_session.flush()

    article = _article(1, cluster.id, now, "Daily One")
    article.primary_topic = "Politics"
    article.subtopic = "courts"
    db_session.add(article)
    db_session.flush()
    db_session.add(
        ClusterArticle(
            cluster_id=cluster.id,
            article_id=article.id,
            similarity_score=0.7,
            heuristic_breakdown={"decision": "create_new_cluster", "selected_score": 1.0},
        )
    )
    db_session.commit()

    response = client.get("/debug/topic-lanes")
    assert response.status_code == 200
    payload = response.json()
    lane = next(item for item in payload["items"] if item["topic"] == "Politics" and item["subtopic"] == "courts")
    assert lane["article_count"] == 1
    assert lane["hidden_clusters"] == 1
    assert "source_count_below_threshold" in lane["reason_hidden"]


def test_debug_clusters_exposes_low_trust_aggregator_promotion_blocker(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster("google-only-cluster", now)
    cluster.status = "hidden"
    db_session.add(cluster)
    db_session.flush()

    for idx in range(3):
        article = _article(idx + 1, cluster.id, now, "Google News")
        article.raw_payload = {
            "feed": {
                "title": "Google News Business",
                "feed_url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
                "priority": "low",
                "promote_to_home": False,
            }
        }
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=cluster.id,
                article_id=article.id,
                similarity_score=0.7,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.7},
            )
        )

    db_session.commit()

    response = client.get("/debug/clusters")
    assert response.status_code == 200
    item = next(entry for entry in response.json()["items"] if entry["cluster_id"] == "google-only-cluster")
    assert item["promotion_eligible"] is False
    assert any("insufficient_high_quality_sources" in blocker for blocker in item["promotion_blockers"])
    assert item["debug_explanation"]["source_quality_summary"]["low_trust_aggregator"] == 3


def test_api_clusters_filters_out_clusters_below_min_source_count(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    small_cluster = _cluster("small-cluster", now)
    db_session.add(small_cluster)
    db_session.flush()

    for idx in range(1):
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


def test_api_clusters_keeps_low_score_clusters_when_they_are_valid(client, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    low_score_cluster = _cluster("low-score-cluster", now)
    low_score_cluster.score = 0.24
    db_session.add(low_score_cluster)
    db_session.flush()

    for idx in range(3):
        article = _article(idx + 1, low_score_cluster.id, now, f"Publisher {idx}")
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=low_score_cluster.id,
                article_id=article.id,
                similarity_score=0.2,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.2},
            )
        )

    db_session.commit()

    response = client.get("/api/clusters")
    assert response.status_code == 200
    payload = response.json()
    assert any(item["cluster_id"] == "low-score-cluster" for item in payload["items"])
