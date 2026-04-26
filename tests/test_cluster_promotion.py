from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, PipelineStats
from app.services.clustering import cluster_new_articles
from app.services.metrics import update_cluster_metrics


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_api_token": "token",
        "cluster_min_sources_for_api": 3,
        "cluster_emerging_source_count": 3,
    }
    base.update(overrides)
    return Settings(**base)


def _article(
    dedupe_hash: str,
    *,
    title: str,
    normalized_title: str,
    keywords: list[str],
    entities: list[str],
    published_at: datetime,
    publisher: str,
) -> Article:
    return Article(
        external_id=None,
        title=title,
        url=f"https://example.com/{dedupe_hash}",
        canonical_url=f"https://example.com/{dedupe_hash}",
        publisher=publisher,
        published_at=published_at,
        content_text=title,
        raw_payload={"title": title},
        normalized_title=normalized_title,
        keywords=keywords,
        entities=entities,
        dedupe_hash=dedupe_hash,
    )


def _transit_article(idx: int, published_at: datetime, publisher: str) -> Article:
    return _article(
        dedupe_hash=f"promo-transit-{idx}",
        title=f"City Council Transit Expansion Update {idx}",
        normalized_title=f"city council transit expansion update {idx}",
        keywords=["city", "council", "transit", "expansion", "funding", "update"],
        entities=["City Council", "Transit Authority"],
        published_at=published_at,
        publisher=publisher,
    )


def _source_count(db_session: Session, cluster_id: str) -> int:
    return int(
        db_session.scalar(
            select(func.count()).select_from(ClusterArticle).where(ClusterArticle.cluster_id == cluster_id)
        )
        or 0
    )


def test_one_source_cluster_stays_hidden(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(_transit_article(1, now - timedelta(hours=3), "Source One"))
    db_session.commit()

    cluster_new_articles(db_session, _settings())
    db_session.commit()

    cluster = db_session.scalars(select(Cluster)).first()
    assert cluster is not None
    assert cluster.status == "hidden"
    assert _source_count(db_session, cluster.id) == 1
    assert cluster.promoted_at is None
    assert cluster.validation_error is None


def test_two_source_cluster_stays_hidden_when_threshold_is_three(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(_transit_article(1, now - timedelta(hours=3), "Source One"))
    db_session.add(_transit_article(2, now - timedelta(hours=2), "Source Two"))
    db_session.commit()

    cluster_new_articles(db_session, _settings())
    db_session.commit()

    cluster = db_session.scalars(select(Cluster)).first()
    assert cluster is not None
    assert _source_count(db_session, cluster.id) == 2
    assert cluster.status == "hidden"
    assert cluster.promoted_at is None


def test_hidden_cluster_promotes_to_active_preserving_identity_and_first_seen(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    settings = _settings()

    # Phase 1: 1 source -> hidden
    db_session.add(_transit_article(1, now - timedelta(hours=3), "Source One"))
    db_session.commit()
    phase1_result = cluster_new_articles(db_session, settings)
    db_session.commit()

    phase1 = db_session.scalars(select(Cluster)).first()
    assert phase1 is not None
    cluster_id = phase1.id
    first_seen = phase1.first_seen
    phase1_last_updated = phase1.last_updated
    assert phase1.status == "hidden"

    # Phase 2: 2 sources -> still hidden
    db_session.add(_transit_article(2, now - timedelta(hours=2), "Source Two"))
    db_session.commit()
    phase2_result = cluster_new_articles(db_session, settings)
    db_session.commit()

    phase2 = db_session.get(Cluster, cluster_id)
    assert phase2 is not None
    assert phase2.status == "hidden"
    assert _source_count(db_session, cluster_id) == 2
    assert phase2.first_seen == first_seen

    # Phase 3: 3rd related source -> promotion
    db_session.add(_transit_article(3, now - timedelta(hours=1), "Source Three"))
    db_session.commit()
    phase3_result = cluster_new_articles(db_session, settings)
    db_session.commit()

    phase3 = db_session.get(Cluster, cluster_id)
    assert phase3 is not None
    assert phase3.id == cluster_id
    assert phase3.first_seen == first_seen
    assert phase3.last_updated > phase1_last_updated
    assert phase3.status == "active"
    assert phase3.promoted_at is not None
    assert phase3.previous_status == "hidden"
    assert _source_count(db_session, cluster_id) == 3
    assert phase3.validation_error is None

    # Promotion should not create replacement/duplicate active clusters.
    total_clusters = int(db_session.scalar(select(func.count()).select_from(Cluster)) or 0)
    active_clusters = int(db_session.scalar(select(func.count()).select_from(Cluster).where(Cluster.status == "active")) or 0)
    assert total_clusters == 1
    assert active_clusters == 1
    assert phase1_result.promoted_count == 0
    assert phase2_result.promoted_count == 0
    assert phase3_result.promoted_count == 1
    assert phase3_result.promotion_attempts >= 1
    assert phase3_result.promotion_failures == 0


def test_unrelated_article_does_not_promote_hidden_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    settings = _settings()

    db_session.add(_transit_article(1, now - timedelta(hours=3), "Source One"))
    db_session.commit()
    cluster_new_articles(db_session, settings)
    db_session.commit()

    hidden_cluster = db_session.scalars(select(Cluster)).first()
    assert hidden_cluster is not None
    hidden_cluster_id = hidden_cluster.id
    assert hidden_cluster.status == "hidden"

    db_session.add(
        _article(
            dedupe_hash="promo-unrelated-1",
            title="Tech Firm Announces Chip Roadmap",
            normalized_title="tech firm announces chip roadmap",
            keywords=["tech", "chip", "roadmap", "earnings"],
            entities=["Tech Firm"],
            published_at=now - timedelta(hours=1),
            publisher="Business Daily",
        )
    )
    db_session.commit()
    cluster_new_articles(db_session, settings)
    db_session.commit()

    original_cluster = db_session.get(Cluster, hidden_cluster_id)
    assert original_cluster is not None
    assert original_cluster.status == "hidden"
    assert _source_count(db_session, hidden_cluster_id) == 1
    assert original_cluster.promoted_at is None

    total_clusters = int(db_session.scalar(select(func.count()).select_from(Cluster)) or 0)
    assert total_clusters == 2


def test_hidden_cluster_with_enough_sources_can_be_promoted_without_new_articles(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    settings = _settings()

    cluster = Cluster(
        id="stuck-hidden-cluster",
        headline="City Council Transit Expansion Update",
        summary="Three outlets are covering the transit expansion with consistent facts and new detail.",
        what_changed="Coverage moved from the initial announcement to broader reporting on funding and routes.",
        why_it_matters="The change affects transit availability and costs, and sustained updates indicate continuing relevance.",
        first_seen=now - timedelta(hours=4),
        last_updated=now - timedelta(hours=1),
        score=0.22,
        status="hidden",
        normalized_headline="city council transit expansion update",
        keywords=["city", "council", "transit", "expansion"],
        entities=["City Council", "Transit Authority"],
        validation_error=None,
    )
    db_session.add(cluster)
    db_session.flush()

    for idx in range(3):
        article = _transit_article(idx + 1, now - timedelta(hours=3 - idx), f"Source {idx + 1}")
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=cluster.id,
                article_id=article.id,
                similarity_score=0.22,
                heuristic_breakdown={"decision": "attach_existing_cluster", "selected_score": 0.22},
            )
        )

    db_session.commit()

    result = cluster_new_articles(db_session, settings)
    db_session.commit()

    promoted = db_session.get(Cluster, cluster.id)
    assert promoted is not None
    assert promoted.status == "active"
    assert promoted.promoted_at is not None
    assert promoted.validation_error is None
    assert result.promoted_count == 1


def test_promotion_metrics_counters_update(db_session: Session) -> None:
    update_cluster_metrics(
        db_session,
        created=0,
        updated=1,
        promoted=1,
        hidden_total=4,
        active_total=7,
        promotion_attempts=2,
        promotion_failures=1,
    )
    db_session.commit()

    stats = db_session.get(PipelineStats, 1)
    assert stats is not None
    assert stats.clusters_promoted_total == 1
    assert stats.clusters_hidden_total == 4
    assert stats.clusters_active_total == 7
    assert stats.cluster_promotion_attempts_total == 2
    assert stats.cluster_promotion_failures_total == 1
    assert stats.latest_candidate_clusters_created == 0
    assert stats.latest_clusters_updated == 1
    assert stats.latest_clusters_hidden == 4
    assert stats.latest_clusters_promoted == 1
    assert stats.latest_visible_clusters == 7
