from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.services.enrichment import build_what_changed
from app.services.clustering import _refresh_related_clusters, cluster_new_articles
from app.services.topics import derive_topic_from_text


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "miniflux_api_token": "token",
        "cluster_min_sources_for_api": 1,
    }
    base.update(overrides)
    return Settings(**base)


def _article(
    dedupe_hash: str,
    title: str,
    normalized_title: str,
    keywords: list[str],
    entities: list[str],
    published_at: datetime,
    publisher: str = "Example News",
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


def test_near_duplicate_titles_attach_to_same_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="a1",
            title="City Council Approves Transit Plan",
            normalized_title="city council approves transit plan",
            keywords=["city", "council", "transit", "plan"],
            entities=["City Council"],
            published_at=now - timedelta(hours=2),
        )
    )
    db_session.add(
        _article(
            dedupe_hash="a2",
            title="City Council Approves New Transit Plan",
            normalized_title="city council approves new transit plan",
            keywords=["city", "council", "transit", "plan"],
            entities=["City Council"],
            published_at=now - timedelta(hours=1),
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.updated_count == 2
    assert result.attach_decisions == 1
    assert db_session.query(Cluster).count() == 1


def test_cluster_new_articles_creates_separate_clusters_for_unrelated_coverage(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="b1",
            title="Wildfire Grows in Northern Region",
            normalized_title="wildfire grows in northern region",
            keywords=["wildfire", "northern", "region"],
            entities=["Northern Region"],
            published_at=now - timedelta(hours=2),
        )
    )
    db_session.add(
        _article(
            dedupe_hash="b2",
            title="Tech Firm Announces Quarterly Earnings",
            normalized_title="tech firm announces quarterly earnings",
            keywords=["tech", "firm", "quarterly", "earnings"],
            entities=["Tech Firm"],
            published_at=now - timedelta(hours=1),
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert db_session.query(Cluster).count() == 2


def test_close_time_same_topic_without_semantic_overlap_creates_new_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="time-only-1",
        title="Transit agency board approves strike settlement",
        normalized_title="transit agency board approves strike settlement",
        keywords=["agency", "board", "strike", "settlement"],
        entities=["Transit Workers Union"],
        published_at=now - timedelta(minutes=20),
        publisher="Metro Daily",
    )
    first.topic = "Transit"
    second = _article(
        dedupe_hash="time-only-2",
        title="Transit museum opens new photography exhibit",
        normalized_title="transit museum opens new photography exhibit",
        keywords=["museum", "photography", "exhibit", "opens"],
        entities=["City Museum"],
        published_at=now - timedelta(minutes=5),
        publisher="Culture Wire",
    )
    second.topic = "Transit"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert result.signal_rejected >= 1
    assert db_session.query(Cluster).count() == 2

    created_links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = created_links[-1].heuristic_breakdown
    assert second_breakdown["decision"] == "create_new_cluster"
    assert second_breakdown["decision_reason"] == "strongest_candidate_failed_semantic_gate"
    assert second_breakdown["components"]["time_proximity"] > 0.9
    assert second_breakdown["thresholds_met"]["signal_gate_passed"] is False


def test_generic_stopword_keyword_overlap_does_not_attach(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="stopword-1",
        title="Solar farm opens near county airport",
        normalized_title="solar farm opens near county airport",
        keywords=["the", "and", "for", "solar"],
        entities=[],
        published_at=now - timedelta(minutes=15),
        publisher="Energy Desk",
    )
    first.topic = "Infrastructure"
    second = _article(
        dedupe_hash="stopword-2",
        title="Court hears appeal in fraud case",
        normalized_title="court hears appeal in fraud case",
        keywords=["the", "and", "for", "court"],
        entities=[],
        published_at=now - timedelta(minutes=5),
        publisher="Justice Wire",
    )
    second.topic = "Infrastructure"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2

    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert second_breakdown["decision"] == "create_new_cluster"
    assert second_breakdown["overlap_counts"]["keyword_overlap"] == 0
    assert second_breakdown["thresholds_met"]["signal_gate_passed"] is False


def test_clustering_batch_size_limits_articles_per_cycle(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    fixtures = [
        ("batch-0", "Harbor ferry terminal reopens after inspection", ["harbor", "ferry", "terminal"], ["Harbor Authority"]),
        ("batch-1", "County hospital launches rural clinic program", ["county", "hospital", "clinic"], ["County Hospital"]),
        ("batch-2", "Solar company reports battery plant expansion", ["solar", "battery", "plant"], ["Solar Works"]),
    ]
    for index, (dedupe_hash, title, keywords, entities) in enumerate(fixtures):
        db_session.add(
            _article(
                dedupe_hash=dedupe_hash,
                title=title,
                normalized_title=title.lower(),
                keywords=keywords,
                entities=entities,
                published_at=now + timedelta(minutes=index),
            )
        )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings(clustering_batch_size=2))
    db_session.commit()

    assert result.created_count == 2
    assert db_session.query(ClusterArticle).count() == 2
    assert db_session.query(Cluster).count() == 2


def test_weak_text_overlap_with_same_named_entity_and_event_attaches(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="entity-event-1",
        title="Governor orders emergency inspection after Pine Ridge Dam cracks",
        normalized_title="governor orders emergency inspection after pine ridge dam cracks",
        keywords=["governor", "emergency", "inspection", "cracks"],
        entities=["Pine Ridge Dam"],
        published_at=now - timedelta(hours=2),
        publisher="State Ledger",
    )
    first.topic = "Pine Ridge Dam"
    second = _article(
        dedupe_hash="entity-event-2",
        title="Officials publish evacuation timeline near Pine Ridge Dam",
        normalized_title="officials publish evacuation timeline near pine ridge dam",
        keywords=["officials", "evacuation", "timeline", "near"],
        entities=["Pine Ridge Dam"],
        published_at=now - timedelta(minutes=40),
        publisher="Valley Herald",
    )
    second.topic = "Pine Ridge Dam"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    assert db_session.query(Cluster).count() == 1

    attached_link = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())[-1]
    breakdown = attached_link.heuristic_breakdown
    assert breakdown["decision"] == "attach_existing_cluster"
    assert "meaningful_entity_overlap" in breakdown["signal_reasons"]
    assert breakdown["overlap_counts"]["entity_overlap"] == 1


def test_article_attaches_to_existing_cluster_on_subsequent_run(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="c1",
            title="State Agency Announces Water Conservation Plan",
            normalized_title="state agency announces water conservation plan",
            keywords=["state", "agency", "water", "conservation", "plan"],
            entities=["State Agency"],
            published_at=now - timedelta(hours=3),
            publisher="Regional Daily",
        )
    )
    db_session.commit()

    first = cluster_new_articles(db_session, _settings())
    db_session.commit()
    assert first.created_count == 1

    db_session.add(
        _article(
            dedupe_hash="c2",
            title="State Agency Expands Water Conservation Plan",
            normalized_title="state agency expands water conservation plan",
            keywords=["state", "agency", "water", "conservation", "plan"],
            entities=["State Agency"],
            published_at=now - timedelta(hours=1),
            publisher="Metro Chronicle",
        )
    )
    db_session.commit()

    second = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert second.created_count == 0
    assert second.attach_decisions == 1
    assert db_session.query(Cluster).count() == 1

    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    assert len(links) == 2
    assert links[-1].heuristic_breakdown["decision"] == "attach_existing_cluster"


def test_cluster_article_decision_log_is_structured(caplog, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="log-1",
            title="City Council Approves Transit Plan",
            normalized_title="city council approves transit plan",
            keywords=["city", "council", "transit", "plan"],
            entities=["City Council"],
            published_at=now - timedelta(hours=2),
        )
    )
    db_session.add(
        _article(
            dedupe_hash="log-2",
            title="City Council Expands Transit Plan",
            normalized_title="city council expands transit plan",
            keywords=["city", "council", "transit", "plan"],
            entities=["City Council"],
            published_at=now - timedelta(hours=1),
        )
    )
    db_session.commit()

    with caplog.at_level(logging.INFO, logger="app.services.clustering"):
        cluster_new_articles(db_session, _settings())
    db_session.commit()

    log_records = [record for record in caplog.records if record.getMessage().startswith("cluster_article_decision ")]
    assert log_records
    payload = json.loads(log_records[-1].getMessage().split("cluster_article_decision ", 1)[1])
    assert payload["decision"] == "attach_existing_cluster"
    assert payload["strongest_candidate_cluster_id"]
    assert payload["title_similarity"] > 0
    assert payload["entity_overlap"] == 1
    assert payload["keyword_overlap"] >= 2
    assert payload["time_proximity"] > 0
    assert payload["signal_gate_passed"] is True
    assert payload["reason"] in {"attached_to_existing_cluster", "attached_to_existing_cluster_via_override"}


def test_timeline_deduplicates_repetitive_same_publisher_updates(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="d1",
            title="Mayor Announces Transit Expansion",
            normalized_title="mayor announces transit expansion",
            keywords=["mayor", "transit", "expansion"],
            entities=["Mayor"],
            published_at=now - timedelta(hours=3),
            publisher="City Wire",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="d2",
            title="Mayor Announces Transit Expansion Plan",
            normalized_title="mayor announces transit expansion plan",
            keywords=["mayor", "transit", "expansion"],
            entities=["Mayor"],
            published_at=now - timedelta(hours=2, minutes=30),
            publisher="City Wire",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="d3",
            title="Commuter Group Reacts to Transit Expansion",
            normalized_title="commuter group reacts to transit expansion",
            keywords=["commuter", "group", "transit", "expansion"],
            entities=["Commuter Group"],
            published_at=now - timedelta(hours=1),
            publisher="Regional Journal",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.timeline_deduplicated >= 1
    cluster = db_session.scalars(select(Cluster)).first()
    assert cluster is not None
    event_count = db_session.query(ClusterTimelineEvent).filter(ClusterTimelineEvent.cluster_id == cluster.id).count()
    assert event_count < 3


def test_sample_like_transit_articles_merge_into_publishable_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="s1",
            title="City Council Approves Transit Expansion Plan",
            normalized_title="city council approves transit expansion plan",
            keywords=["city", "council", "expansion", "transit", "and", "approved", "details", "funding", "plan"],
            entities=[],
            published_at=now - timedelta(hours=5),
            publisher="Metro Daily",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="s2",
            title="Regional Leaders React to Transit Expansion Funding",
            normalized_title="regional leaders react to transit expansion funding",
            keywords=["expansion", "funding", "leaders", "regional", "transit", "approved", "package", "react", "the"],
            entities=[],
            published_at=now - timedelta(hours=2),
            publisher="Regional Wire",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="s3",
            title="Transit Agencies Publish First Implementation Timeline",
            normalized_title="transit agencies publish first implementation timeline",
            keywords=["agencies", "implementation", "transit", "expected", "milestones", "publish", "the", "timeline", "vote"],
            entities=[],
            published_at=now - timedelta(hours=1),
            publisher="Transport Bulletin",
        )
    )
    db_session.commit()

    result = cluster_new_articles(
        db_session,
        _settings(cluster_min_sources_for_api=3),
    )
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 2
    assert db_session.query(Cluster).count() == 1

    cluster = db_session.scalars(select(Cluster)).first()
    assert cluster is not None
    assert cluster.validation_error is None
    assert len(cluster.source_links) == 3
    assert cluster.key_facts
    assert any("3 sources" in fact for fact in cluster.key_facts)


def test_cluster_topics_are_persisted_for_articles_and_clusters(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="topic-1",
            title="State Agency Announces Water Conservation Plan",
            normalized_title="state agency announces water conservation plan",
            keywords=["state", "agency", "water", "conservation", "plan"],
            entities=["State Agency"],
            published_at=now - timedelta(hours=3),
            publisher="Regional Daily",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="topic-2",
            title="State Agency Expands Water Conservation Plan",
            normalized_title="state agency expands water conservation plan",
            keywords=["state", "agency", "water", "conservation", "plan"],
            entities=["State Agency"],
            published_at=now - timedelta(hours=1),
            publisher="Metro Chronicle",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    cluster = db_session.scalars(select(Cluster)).first()
    assert cluster is not None
    assert cluster.topic
    assert result.created_count == 1

    articles = list(db_session.scalars(select(Article).order_by(Article.id.asc())).all())
    assert all(article.topic for article in articles)
    assert len({article.topic for article in articles}) == 1
    assert articles[0].topic == cluster.topic


def test_topic_mismatch_forces_new_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)

    first = _article(
        dedupe_hash="topic-match-1",
        title="US soldier charged with using Polymarket to bet on Nicolas Maduro abduction",
        normalized_title="us soldier charged with using polymarket to bet on nicolas maduro abduction",
        keywords=["us", "soldier", "polymarket", "maduro", "bet"],
        entities=["Nicolas Maduro", "Polymarket"],
        published_at=now - timedelta(hours=2),
        publisher="Al Jazeera",
    )
    first.topic = "Nicolas Maduro"
    second = _article(
        dedupe_hash="topic-match-2",
        title="French police probe suspected weather device tampering after odd Polymarket bet",
        normalized_title="french police probe suspected weather device tampering after odd polymarket bet",
        keywords=["french", "police", "weather", "polymarket", "bet"],
        entities=["French Police", "Polymarket"],
        published_at=now - timedelta(hours=1),
        publisher="NPR Topics",
    )
    second.topic = "Polymarket"

    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert db_session.query(Cluster).count() == 2


def _cluster_with_sources(
    db_session: Session,
    *,
    cluster_id: str,
    now: datetime,
    topic: str,
    keywords: list[str],
    entities: list[str],
    status: str = "active",
    validation_error: str | None = None,
) -> Cluster:
    cluster = Cluster(
        id=cluster_id,
        headline=f"{topic} Story Advances",
        summary="Multiple sources are covering the story with enough detail for public display.",
        what_changed="Coverage moved from initial reports to broader updates.",
        why_it_matters="Sustained coverage indicates continuing public relevance.",
        first_seen=now - timedelta(hours=1),
        last_updated=now,
        score=0.7,
        status=status,
        normalized_headline=f"{topic.lower()} story advances",
        keywords=keywords,
        entities=entities,
        topic=topic,
        validation_error=validation_error,
    )
    db_session.add(cluster)
    db_session.flush()

    for index, publisher in enumerate(["Daily One", "Daily Two"], start=1):
        article = _article(
            dedupe_hash=f"{cluster_id}-{index}",
            title=f"{topic} update {index}",
            normalized_title=f"{topic.lower()} update {index}",
            keywords=keywords,
            entities=entities,
            published_at=now - timedelta(minutes=index),
            publisher=publisher,
        )
        article.topic = topic
        db_session.add(article)
        db_session.flush()
        db_session.add(
            ClusterArticle(
                cluster_id=cluster.id,
                article_id=article.id,
                similarity_score=0.7,
                heuristic_breakdown={"decision": "attach_existing_cluster"},
            )
        )

    return cluster


def test_related_clusters_require_semantic_overlap_and_public_visibility(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    base = _cluster_with_sources(
        db_session,
        cluster_id="base-story",
        now=now,
        topic="Transit",
        keywords=["transit", "budget", "service"],
        entities=["City Council"],
    )
    related = _cluster_with_sources(
        db_session,
        cluster_id="related-story",
        now=now - timedelta(minutes=3),
        topic="Transit",
        keywords=["transit", "routes", "service"],
        entities=["City Council"],
    )
    hidden = _cluster_with_sources(
        db_session,
        cluster_id="hidden-related-story",
        now=now - timedelta(minutes=4),
        topic="Transit",
        keywords=["transit", "budget", "service"],
        entities=["City Council"],
        status="hidden",
        validation_error="manual block",
    )
    time_only = _cluster_with_sources(
        db_session,
        cluster_id="time-only-story",
        now=now - timedelta(minutes=1),
        topic="Weather",
        keywords=["storm", "rain", "forecast"],
        entities=["Weather Service"],
    )

    db_session.flush()
    _refresh_related_clusters(db_session, _settings(cluster_min_sources_for_api=2))

    assert base.related_cluster_ids == [related.id]
    assert related.related_cluster_ids == [base.id]
    assert hidden.id not in base.related_cluster_ids
    assert time_only.id not in base.related_cluster_ids
    assert base.id not in time_only.related_cluster_ids


def test_war_adjacent_articles_do_not_collapse_into_one_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="wa1",
            title="Trump may talk of regime infighting, but Iran seems united by strategy born of war",
            normalized_title="trump may talk of regime infighting but iran seems united by strategy born of war",
            keywords=["trump", "iran", "war", "strategy", "regime", "infighting"],
            entities=["Trump", "Iran"],
            published_at=now - timedelta(hours=3),
        )
    )
    db_session.add(
        _article(
            dedupe_hash="wa2",
            title="US soldier involved in Maduro raid charged over alleged bets on capture",
            normalized_title="us soldier involved in maduro raid charged over alleged bets on capture",
            keywords=["us", "soldier", "maduro", "raid", "capture", "bets"],
            entities=["Maduro"],
            published_at=now - timedelta(hours=1),
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert db_session.query(Cluster).count() == 2


def test_what_changed_filters_noise_terms() -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="wc1",
        title="Trump may talk of regime infighting, but Iran seems united by strategy born of war",
        normalized_title="trump may talk of regime infighting but iran seems united by strategy born of war",
        keywords=["trump", "iran", "war", "strategy", "regime", "infighting"],
        entities=["Trump", "Iran"],
        published_at=now - timedelta(hours=3),
        publisher="World news | The Guardian",
    )
    latest = _article(
        dedupe_hash="wc2",
        title="Trump claims US has total control over strait of Hormuz after Iran seizes two container ships",
        normalized_title="trump claims us has total control over strait of hormuz after iran seizes two container ships",
        keywords=["trump", "iran", "hormuz", "pentagon", "container", "ships", "but"],
        entities=["Trump", "Iran", "Pentagon"],
        published_at=now - timedelta(hours=1),
        publisher="World news | The Guardian",
    )

    text = build_what_changed("cluster-1", [first, latest])

    assert "but" not in text.lower()
    assert "additional confirmed details" not in text.lower()


def test_topic_builder_prefers_human_subject_labels() -> None:
    assert derive_topic_from_text(
        "How Trump's Iran war is driving military dissent",
        "How Trump's Iran war is driving military dissent",
    ) == "Iran War"
    assert derive_topic_from_text(
        "US Department of Justice watchdog to probe release of Epstein files",
        "US Department of Justice watchdog to probe release of Epstein files",
    ) == "Epstein Files"
    assert derive_topic_from_text(
        "Trump administration moves to reclassify cannabis in major shift that could expand research",
        "Trump administration moves to reclassify cannabis in major shift that could expand research",
    ) == "Trump Admin"
    assert derive_topic_from_text(
        "Didi vs Modi: A Test for the Hindu Right in India's Bengali Heartland",
        "Didi vs Modi: A Test for the Hindu Right in India's Bengali Heartland",
    ) == "Didi Modi"
    assert derive_topic_from_text(
        "Alibaba's Qwen AI is coming to cars, allowing drivers order food and book hotels by voice",
        "Alibaba's Qwen AI is coming to cars, allowing drivers order food and book hotels by voice",
    ) == "Alibaba Qwen"
    assert derive_topic_from_text(
        "In Britain, 7 Unelected Lords Are Helping to Block an Assisted Dying Bill",
        "In Britain, 7 Unelected Lords Are Helping to Block an Assisted Dying Bill",
    ) == "Assisted Dying"
    assert derive_topic_from_text(
        "Europe Mulls What Mutual Defense Looks Like Outside NATO",
        "Europe Mulls What Mutual Defense Looks Like Outside NATO",
    ) == "Mutual Defense"
    assert derive_topic_from_text(
        "Actor felt mocked by Rebel Wilson's wife in Instagram post referencing Finding Nemo, court hears",
        "Actor felt mocked by Rebel Wilson's wife in Instagram post referencing Finding Nemo, court hears",
    ) == "Instagram Post"
    assert derive_topic_from_text(
        "Largest-ever ban on toxic chemicals in EU hit by extremely frustrating delays",
        "Largest-ever ban on toxic chemicals in EU hit by extremely frustrating delays",
    ) == "Toxic Chemicals"
    assert derive_topic_from_text(
        "Anthony Albanese accused of caving to gas companies as Labor set to reject new export tax",
        "Anthony Albanese accused of caving to gas companies as Labor set to reject new export tax",
    ) == "Anthony Albanese"
    assert derive_topic_from_text(
        "Trump tells BBC that King's visit could absolutely help repair relations with UK",
        "Trump tells BBC that King's visit could absolutely help repair relations with UK",
    ) == "King Visit"
    assert derive_topic_from_text(
        "US soldier involved in Maduro raid charged over alleged bets on capture",
        "US soldier involved in Maduro raid charged over alleged bets on capture",
    ) == "Maduro Raid"
    assert derive_topic_from_text(
        "2 young people arrested in alleged plot to attack Houston synagogue",
        "2 young people arrested in alleged plot to attack Houston synagogue",
    ) == "Houston Synagogue"
    assert derive_topic_from_text(
        "Australia news live: US approves first major Aukus submarine contract; Harvey Norman facing class action for alleged 'misleading' ads",
        "Australia news live: US approves first major Aukus submarine contract; Harvey Norman facing class action for alleged 'misleading' ads",
    ) == "Aukus Submarine"
    assert derive_topic_from_text(
        "China's DeepSeek releases preview of long-awaited V4 model as AI race intensifies",
        "China's DeepSeek releases preview of long-awaited V4 model as AI race intensifies",
    ) == "DeepSeek Model"
    assert derive_topic_from_text(
        "China's DeepSeek unveils latest models a year after upending global tech",
        "China's DeepSeek unveils latest models a year after upending global tech",
    ) == "DeepSeek Models"
    assert derive_topic_from_text(
        "US soldier arrested for $400K winning Polymarket bets on Maduro capture, DOJ says",
        "US soldier arrested for $400K winning Polymarket bets on Maduro capture, DOJ says",
    ) == "Maduro Capture"
    assert derive_topic_from_text(
        "Soldier Used Classified Information to Bet on Maduro’s Ouster, U.S. Says",
        "Soldier Used Classified Information to Bet on Maduro’s Ouster, U.S. Says",
    ) == "Maduro Ouster"
