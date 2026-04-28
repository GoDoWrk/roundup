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


def test_shared_keywords_without_primary_entity_creates_new_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="entity-required-1",
        title="Transit funding plan advances after board vote",
        normalized_title="transit funding plan advances after board vote",
        keywords=["transit", "funding", "plan", "board", "vote"],
        entities=[],
        published_at=now - timedelta(hours=2),
        publisher="Metro Daily",
    )
    first.topic = "Transit"
    second = _article(
        dedupe_hash="entity-required-2",
        title="Transit funding plan draws regional response",
        normalized_title="transit funding plan draws regional response",
        keywords=["transit", "funding", "plan", "regional", "response"],
        entities=[],
        published_at=now - timedelta(hours=1),
        publisher="Regional Wire",
    )
    second.topic = "Transit"
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
    assert second_breakdown["candidate_rejection_reason"] == "missing_primary_entity_overlap"
    assert second_breakdown["thresholds_met"]["primary_entity_overlap_met"] is False


def test_same_source_update_chain_can_attach_without_named_entity_overlap(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="same-source-1",
        title="Transit agency approves station repair funding",
        normalized_title="transit agency approves station repair funding",
        keywords=["transit", "agency", "station", "funding", "repairs"],
        entities=[],
        published_at=now - timedelta(minutes=40),
        publisher="Metro Daily",
    )
    first.topic = "Transit"
    second = _article(
        dedupe_hash="same-source-2",
        title="Transit agency details station repair funding timeline",
        normalized_title="transit agency details station repair funding timeline",
        keywords=["transit", "agency", "station", "funding", "timeline"],
        entities=[],
        published_at=now - timedelta(minutes=10),
        publisher="Metro Daily",
    )
    second.topic = "Transit"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert "same_source_update_chain" in second_breakdown["signal_reasons"]
    assert second_breakdown["thresholds_met"]["primary_entity_overlap_met"] is False
    assert second_breakdown["thresholds_met"]["same_source_update_chain_met"] is True
    assert second_breakdown["overlap_counts"]["title_token_overlap"] >= 2


def test_same_source_byline_overlap_does_not_merge_unrelated_articles(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="planetizen-1",
        title="Houston pedestrian promenade on track for World Cup crowds",
        normalized_title="houston pedestrian promenade on track for world cup crowds",
        keywords=["diana", "ionescu", "planetizen", "geography", "houston", "promenade"],
        entities=["Diana Ionescu"],
        published_at=now - timedelta(hours=2),
        publisher="Planetizen",
    )
    second = _article(
        dedupe_hash="planetizen-2",
        title="APA conference draws 4,000 urban planners to Detroit this weekend",
        normalized_title="apa conference draws 4000 urban planners to detroit this weekend",
        keywords=["diana", "ionescu", "planetizen", "geography", "detroit", "conference"],
        entities=["Diana Ionescu"],
        published_at=now - timedelta(hours=1),
        publisher="Planetizen",
    )
    first.topic = "Diana Ionescu"
    second.topic = "Diana Ionescu"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert second_breakdown["candidate_rejection_reason"] == "weak_primary_entity_context"
    assert second_breakdown["thresholds_met"]["primary_entity_overlap_met"] is True
    assert second_breakdown["thresholds_met"]["title_primary_entity_overlap_met"] is False


def test_topic_followup_requires_primary_entity_in_title(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="topic-followup-1",
        title="Israeli strikes kill 14 in Lebanon as Israel warns residents beyond buffer zone",
        normalized_title="israeli strikes kill 14 in lebanon as israel warns residents beyond buffer zone",
        keywords=["israeli", "strikes", "lebanon", "security"],
        entities=["Israel", "Iran", "Lebanon"],
        published_at=now - timedelta(hours=2),
        publisher="Reuters",
    )
    first.topic = "Iran War"
    unrelated_context = _article(
        dedupe_hash="topic-followup-2",
        title="National security concerns rise after strikes beyond buffer zone",
        normalized_title="national security concerns rise after strikes beyond buffer zone",
        keywords=["national", "security", "strikes", "buffer"],
        entities=["Israel", "Iran"],
        published_at=now - timedelta(hours=1),
        publisher="Environment Desk",
    )
    unrelated_context.topic = "Iran War"
    db_session.add(first)
    db_session.add(unrelated_context)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2

    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert second_breakdown["candidate_rejection_reason"] == "weak_primary_entity_context"
    assert second_breakdown["thresholds_met"]["primary_entity_overlap_met"] is True
    assert second_breakdown["thresholds_met"]["title_primary_entity_overlap_met"] is False
    assert "topic_followup_continuity" not in second_breakdown["signal_reasons"]


def test_low_trust_aggregator_context_does_not_attach_without_near_duplicate_title(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    official = _article(
        dedupe_hash="official-local-1",
        title="Phoenix police arrest suspect after armed robbery near downtown",
        normalized_title="phoenix police arrest suspect after armed robbery near downtown",
        keywords=["phoenix", "police", "armed", "robbery", "suspect"],
        entities=["Phoenix Police"],
        published_at=now - timedelta(hours=2),
        publisher="Phoenix Police Department",
    )
    official.raw_payload = {"feed": {"feed_url": "https://www.phoenix.gov/newsroom/rss", "title": "Phoenix.gov"}}
    google = _article(
        dedupe_hash="google-local-1",
        title="Juveniles detained after an armed robbery in Phoenix - 12News",
        normalized_title="juveniles detained after an armed robbery in phoenix 12news",
        keywords=["phoenix", "armed", "robbery", "detained"],
        entities=["Phoenix"],
        published_at=now - timedelta(hours=1),
        publisher="Google News",
    )
    google.raw_payload = {"feed": {"feed_url": "https://news.google.com/rss/search?q=Phoenix", "title": "Google News"}}
    db_session.add(official)
    db_session.add(google)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    google_breakdown = links[-1].heuristic_breakdown
    assert google_breakdown["candidate_rejection_reason"] == "low_trust_aggregator_attach_blocked"
    assert google_breakdown["membership_rejection_status"] == "low_trust_aggregator_only"


def test_service_finance_does_not_merge_with_trump_white_house_story(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="poison-finance-1",
            title="The 7 best high-yield savings accounts of April 2023",
            normalized_title="the 7 best high yield savings accounts of april 2023",
            keywords=["best", "high-yield", "savings", "accounts", "april"],
            entities=[],
            published_at=now - timedelta(hours=2),
            publisher="Affiliate Finance",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="poison-trump-1",
            title="Donald Trump to discuss White House press dinner shooting on 60 Minutes",
            normalized_title="donald trump to discuss white house press dinner shooting on 60 minutes",
            keywords=["trump", "white", "house", "dinner", "shooting"],
            entities=["Donald Trump", "White House"],
            published_at=now - timedelta(hours=1),
            publisher="CBS News",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    trump_breakdown = links[-1].heuristic_breakdown
    assert trump_breakdown["membership_rejection_status"] in {
        "rejected_content_class_mismatch",
        "rejected_low_similarity",
        "candidate_needs_more_sources",
    }


def test_trump_white_house_story_does_not_merge_with_ben_sasse_cancer_interview(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="poison-trump-2",
            title="Donald Trump to discuss White House press dinner shooting on 60 Minutes",
            normalized_title="donald trump to discuss white house press dinner shooting on 60 minutes",
            keywords=["trump", "white", "house", "dinner", "shooting", "minutes"],
            entities=["Donald Trump", "White House"],
            published_at=now - timedelta(hours=2),
            publisher="CBS News",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="poison-sasse-1",
            title="Ben Sasse, living with cancer, sees an opportunity in living on a deadline",
            normalized_title="ben sasse living with cancer sees an opportunity in living on a deadline",
            keywords=["ben", "sasse", "cancer", "deadline", "living", "america"],
            entities=["Ben Sasse"],
            published_at=now - timedelta(hours=1),
            publisher="CBS News",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2


def test_home_equity_cashout_does_not_merge_with_general_business_news(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="poison-home-equity",
            title="Turn Your Rising Home Equity Into Cash You Can Use",
            normalized_title="turn your rising home equity into cash you can use",
            keywords=["home", "equity", "cash", "use"],
            entities=[],
            published_at=now - timedelta(hours=2),
            publisher="Lending Partner",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="business-news-1",
            title="Federal Reserve officials signal rate decision after inflation report",
            normalized_title="federal reserve officials signal rate decision after inflation report",
            keywords=["federal", "reserve", "inflation", "rates", "decision"],
            entities=["Federal Reserve"],
            published_at=now - timedelta(hours=1),
            publisher="Reuters",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2


def test_stale_service_finance_does_not_merge_with_current_business_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="current-business-1",
            title="Reuters reports Federal Reserve rate outlook after inflation data",
            normalized_title="reuters reports federal reserve rate outlook after inflation data",
            keywords=["federal", "reserve", "rate", "inflation", "outlook"],
            entities=["Federal Reserve", "Reuters"],
            published_at=now - timedelta(hours=2),
            publisher="Reuters",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="stale-finance-1",
            title="Best CD rates of March 2024",
            normalized_title="best cd rates of march 2024",
            keywords=["best", "cd", "rates", "march"],
            entities=[],
            published_at=now - timedelta(hours=1),
            publisher="Affiliate Finance",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2


def test_ben_sasse_interview_updates_merge(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="sasse-1",
            title="Former Sen. Ben Sasse, dying of cancer, on his hopes for America's future",
            normalized_title="former sen ben sasse dying of cancer on his hopes for americas future",
            keywords=["ben", "sasse", "cancer", "future", "america"],
            entities=["Ben Sasse"],
            published_at=now - timedelta(hours=2),
            publisher="CBS News",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="sasse-2",
            title="Extended interview: Ben Sasse on lessons for America",
            normalized_title="extended interview ben sasse on lessons for america",
            keywords=["ben", "sasse", "interview", "lessons", "america"],
            entities=["Ben Sasse"],
            published_at=now - timedelta(hours=1),
            publisher="CBS News",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    assert db_session.query(Cluster).count() == 1


def test_same_story_from_wire_and_public_media_merges_on_primary_entity(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    sources = ["AP", "Reuters", "NPR", "PBS"]
    for index, publisher in enumerate(sources):
        db_session.add(
            _article(
                dedupe_hash=f"wire-entity-{index}",
                title=f"{publisher} reports Pine Ridge Dam evacuation order after structural cracks",
                normalized_title=f"{publisher.lower()} reports pine ridge dam evacuation order after structural cracks",
                keywords=["pine", "ridge", "dam", "evacuation", "cracks"],
                entities=["Pine Ridge Dam"],
                published_at=now - timedelta(minutes=40 - index),
                publisher=publisher,
            )
        )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 3
    assert db_session.query(Cluster).count() == 1


def test_local_phoenix_updates_merge_with_shared_location_and_entity(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    fixtures = [
        ("az-1", "Phoenix officials open cooling centers after heat emergency", "AZCentral"),
        ("az-2", "Phoenix heat emergency prompts more cooling centers", "KJZZ"),
        ("az-3", "Phoenix expands cooling centers during heat emergency", "ABC15"),
    ]
    for index, (dedupe_hash, title, publisher) in enumerate(fixtures):
        db_session.add(
            _article(
                dedupe_hash=dedupe_hash,
                title=title,
                normalized_title=title.lower(),
                keywords=["phoenix", "heat", "emergency", "cooling", "centers"],
                entities=["Phoenix"],
                published_at=now - timedelta(minutes=30 - index),
                publisher=publisher,
            )
        )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 2
    assert db_session.query(Cluster).count() == 1


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
    assert breakdown["overlap_counts"]["entity_overlap"] >= 1


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
    assert payload["entity_overlap"] >= 1
    assert payload["keyword_overlap"] >= 2
    assert "location_overlap" in payload
    assert "source_match" in payload
    assert payload["selected_cluster_id"]
    assert "candidate_cluster_id" in payload
    assert payload["time_proximity"] > 0
    assert payload["signal_gate_passed"] is True
    assert "matched_features" in payload
    assert "ignored_features" in payload
    assert "primary_entity_overlap" in payload["matched_features"]
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
    events = list(db_session.scalars(select(ClusterTimelineEvent.event)).all())
    assert all("Update focuses on" not in event for event in events)
    assert any("reported:" in event for event in events)


def test_sample_like_transit_articles_merge_into_publishable_cluster(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="s1",
            title="City Council Approves Transit Expansion Plan",
            normalized_title="city council approves transit expansion plan",
            keywords=["city", "council", "expansion", "transit", "and", "approved", "details", "funding", "plan"],
            entities=["City Council", "Transit Authority"],
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
            entities=["City Council", "Transit Authority"],
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
            entities=["City Council", "Transit Authority"],
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


def test_near_duplicate_title_does_not_override_distinct_primary_entities(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="entity-conflict-1",
        title="Mayor announces emergency budget plan after storm damage",
        normalized_title="mayor announces emergency budget plan after storm damage",
        keywords=["emergency", "budget", "plan", "storm", "damage"],
        entities=["Phoenix Mayor"],
        published_at=now - timedelta(minutes=20),
        publisher="City Desk",
    )
    first.topic = "Emergency Budget"
    second = _article(
        dedupe_hash="entity-conflict-2",
        title="Governor announces emergency budget plan after storm damage",
        normalized_title="governor announces emergency budget plan after storm damage",
        keywords=["emergency", "budget", "plan", "storm", "damage"],
        entities=["Arizona Governor"],
        published_at=now - timedelta(minutes=10),
        publisher="State Wire",
    )
    second.topic = "Emergency Budget"
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert second_breakdown["candidate_rejection_reason"] == "distinct_primary_entities"
    assert second_breakdown["thresholds_met"]["near_duplicate_title_met"] is True
    assert second_breakdown["thresholds_met"]["primary_entity_conflict_met"] is True
    assert "primary_entity_conflict" in second_breakdown["ignored_features"]


def test_desantis_redistricting_articles_cluster_together(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    first = _article(
        dedupe_hash="desantis-redistricting-1",
        title="DeSantis asks Florida lawmakers to advance redistricting map",
        normalized_title="desantis asks florida lawmakers to advance redistricting map",
        keywords=["desantis", "florida", "redistricting", "map", "lawmakers"],
        entities=["Ron DeSantis", "Florida"],
        published_at=now - timedelta(hours=2),
        publisher="Tallahassee Ledger",
    )
    second = _article(
        dedupe_hash="desantis-redistricting-2",
        title="Florida redistricting push by DeSantis draws new court scrutiny",
        normalized_title="florida redistricting push by desantis draws new court scrutiny",
        keywords=["florida", "redistricting", "desantis", "map", "court"],
        entities=["Ron DeSantis", "Florida"],
        published_at=now - timedelta(hours=1),
        publisher="Capitol Wire",
    )
    db_session.add(first)
    db_session.add(second)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    cluster = db_session.scalars(select(Cluster)).one()
    assert cluster.primary_topic == "Politics"
    assert cluster.subtopic == "redistricting"
    assert cluster.event_type == "redistricting"


def test_unrelated_politics_stories_do_not_merge_with_topic_lane_match(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="politics-redistricting",
            title="DeSantis asks Florida lawmakers to advance redistricting map",
            normalized_title="desantis asks florida lawmakers to advance redistricting map",
            keywords=["desantis", "florida", "redistricting", "map"],
            entities=["Ron DeSantis", "Florida"],
            published_at=now - timedelta(hours=2),
            publisher="Tallahassee Ledger",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="politics-white-house",
            title="White House officials brief Congress on security funding bill",
            normalized_title="white house officials brief congress on security funding bill",
            keywords=["white", "house", "congress", "security", "funding"],
            entities=["White House", "Congress"],
            published_at=now - timedelta(hours=1),
            publisher="National Desk",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    second_breakdown = links[-1].heuristic_breakdown
    assert second_breakdown["decision_reason"] == "no_candidate_clusters"
    assert second_breakdown["candidate_count"] == 0


def test_ai_regulation_stories_cluster_separately_from_ai_lawsuit_stories(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="ai-regulation",
            title="Lawmakers propose AI regulation bill for OpenAI and other model developers",
            normalized_title="lawmakers propose ai regulation bill for openai and other model developers",
            keywords=["ai", "regulation", "bill", "openai", "models"],
            entities=["OpenAI", "Congress"],
            published_at=now - timedelta(hours=2),
            publisher="Tech Policy Daily",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="ai-lawsuit",
            title="OpenAI faces copyright lawsuit over AI training data",
            normalized_title="openai faces copyright lawsuit over ai training data",
            keywords=["openai", "ai", "lawsuit", "copyright", "training"],
            entities=["OpenAI"],
            published_at=now - timedelta(hours=1),
            publisher="Court Tech Wire",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    lawsuit_breakdown = links[-1].heuristic_breakdown
    assert lawsuit_breakdown["candidate_rejection_reason"] == "event_type_conflict"
    assert lawsuit_breakdown["thresholds_met"]["event_type_conflict_met"] is True


def test_health_stories_do_not_merge_with_science_environment_keyword_overlap(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="health-pollution",
            title="Doctors warn pollution exposure is worsening asthma cases",
            normalized_title="doctors warn pollution exposure is worsening asthma cases",
            keywords=["pollution", "health", "asthma", "doctors"],
            entities=["American Medical Association"],
            published_at=now - timedelta(hours=2),
            publisher="Health Desk",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="science-pollution",
            title="Scientists track pollution effects on river wildlife habitat",
            normalized_title="scientists track pollution effects on river wildlife habitat",
            keywords=["pollution", "environment", "scientists", "wildlife"],
            entities=["River Research Institute"],
            published_at=now - timedelta(hours=1),
            publisher="Science Journal",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.candidates_evaluated == 0
    clusters = list(db_session.scalars(select(Cluster).order_by(Cluster.primary_topic.asc())).all())
    assert {cluster.primary_topic for cluster in clusters} == {"Health", "Science"}


def test_uae_opec_energy_articles_from_different_sources_attach(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="uae-opec-1",
            title="UAE oil minister says OPEC output cut begins Monday",
            normalized_title="uae oil minister says opec output cut begins monday",
            keywords=["uae", "opec", "oil", "output", "deal", "energy"],
            entities=["UAE", "OPEC"],
            published_at=now - timedelta(hours=2),
            publisher="Energy Wire",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="uae-opec-2",
            title="OPEC reaches oil output agreement with UAE support",
            normalized_title="opec reaches oil output agreement with uae support",
            keywords=["opec", "oil", "output", "agreement", "uae", "energy"],
            entities=["OPEC", "UAE"],
            published_at=now - timedelta(hours=1),
            publisher="Markets Desk",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    assert result.entity_overlap_attaches == 1
    assert db_session.query(Cluster).count() == 1


def test_king_charles_trump_visit_articles_attach(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="king-charles-trump-1",
            title="King Charles hosts Trump for UK state visit at Windsor",
            normalized_title="king charles hosts trump for uk state visit at windsor",
            keywords=["king", "charles", "trump", "uk", "state", "visit"],
            entities=["King Charles", "Donald Trump", "United Kingdom"],
            published_at=now - timedelta(hours=2),
            publisher="World Service",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="king-charles-trump-2",
            title="Trump meets King Charles during Britain state visit",
            normalized_title="trump meets king charles during britain state visit",
            keywords=["trump", "king", "charles", "britain", "state", "visit"],
            entities=["Donald Trump", "King Charles", "United Kingdom"],
            published_at=now - timedelta(hours=1),
            publisher="Diplomacy Daily",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    assert db_session.query(Cluster).count() == 1


def test_openai_lawsuit_articles_attach_across_named_people(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="openai-lawsuit-1",
            title="Elon Musk lawsuit against OpenAI and Sam Altman advances in court",
            normalized_title="elon musk lawsuit against openai and sam altman advances in court",
            keywords=["elon", "musk", "openai", "sam", "altman", "lawsuit", "court"],
            entities=["Elon Musk", "OpenAI", "Sam Altman"],
            published_at=now - timedelta(hours=2),
            publisher="Tech Court Wire",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="openai-lawsuit-2",
            title="OpenAI asks judge to dismiss Elon Musk suit against Sam Altman",
            normalized_title="openai asks judge to dismiss elon musk suit against sam altman",
            keywords=["openai", "judge", "dismiss", "elon", "musk", "sam", "altman", "lawsuit"],
            entities=["OpenAI", "Elon Musk", "Sam Altman"],
            published_at=now - timedelta(hours=1),
            publisher="AI Policy News",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 1
    assert result.attach_decisions == 1
    cluster = db_session.scalars(select(Cluster)).one()
    assert cluster.primary_topic == "Technology"
    assert cluster.event_type == "legal"


def test_unrelated_business_market_stories_do_not_merge_on_generic_economy_terms(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="business-markets-1",
            title="Fed rate worries push stock markets lower",
            normalized_title="fed rate worries push stock markets lower",
            keywords=["fed", "rates", "stock", "markets", "economy"],
            entities=["Federal Reserve", "S&P 500"],
            published_at=now - timedelta(hours=2),
            publisher="Market Desk",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="business-economy-2",
            title="Oil company earnings lift energy shares despite economy concerns",
            normalized_title="oil company earnings lift energy shares despite economy concerns",
            keywords=["oil", "earnings", "energy", "shares", "economy", "markets"],
            entities=["Exxon Mobil"],
            published_at=now - timedelta(hours=1),
            publisher="Business Wire",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 0
    assert db_session.query(Cluster).count() == 2


def test_environment_articles_require_shared_entity_and_event_type(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="environment-research-1",
            title="Scientists publish Colorado River pollution study",
            normalized_title="scientists publish colorado river pollution study",
            keywords=["scientists", "colorado", "river", "pollution", "study", "environment"],
            entities=["Colorado River Institute"],
            published_at=now - timedelta(hours=3),
            publisher="Science Journal",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="environment-policy-2",
            title="Officials announce pollution rules for coastal wildlife habitat",
            normalized_title="officials announce pollution rules for coastal wildlife habitat",
            keywords=["pollution", "rules", "wildlife", "habitat", "environment"],
            entities=["Coastal Wildlife Agency"],
            published_at=now - timedelta(hours=2),
            publisher="Environment Daily",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="environment-research-3",
            title="Colorado River Institute study links pollution to fish decline",
            normalized_title="colorado river institute study links pollution to fish decline",
            keywords=["colorado", "river", "pollution", "study", "fish", "environment"],
            entities=["Colorado River Institute"],
            published_at=now - timedelta(hours=1),
            publisher="Research Wire",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.created_count == 2
    assert result.attach_decisions == 1
    clusters = list(db_session.scalars(select(Cluster).order_by(Cluster.last_updated.asc())).all())
    assert len(clusters) == 2
    source_counts = sorted(len(cluster.source_links) for cluster in clusters)
    assert source_counts == [1, 2]


def test_candidate_diagnostics_capture_rejected_same_lane_candidates(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        _article(
            dedupe_hash="diagnostic-ai-1",
            title="Lawmakers propose AI regulation bill for OpenAI model developers",
            normalized_title="lawmakers propose ai regulation bill for openai model developers",
            keywords=["ai", "regulation", "bill", "openai", "models"],
            entities=["OpenAI", "Congress"],
            published_at=now - timedelta(hours=2),
            publisher="Tech Policy Daily",
        )
    )
    db_session.add(
        _article(
            dedupe_hash="diagnostic-ai-2",
            title="OpenAI faces copyright lawsuit over AI training data",
            normalized_title="openai faces copyright lawsuit over ai training data",
            keywords=["openai", "ai", "lawsuit", "copyright", "training"],
            entities=["OpenAI"],
            published_at=now - timedelta(hours=1),
            publisher="Court Tech Wire",
        )
    )
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.attach_decisions == 0
    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.id.asc())).all())
    diagnostics = links[-1].heuristic_breakdown["candidate_diagnostics"]
    assert diagnostics
    assert diagnostics[0]["article_headline"] == "OpenAI faces copyright lawsuit over AI training data"
    assert diagnostics[0]["candidate_cluster_headline"]
    assert diagnostics[0]["article_primary_topic"] == "Technology"
    assert diagnostics[0]["cluster_primary_topic"] == "Technology"
    assert diagnostics[0]["final_decision"] == "reject"
    assert diagnostics[0]["rejection_reason"] == "event_type_conflict"


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


def test_mali_camara_story_rejects_gaza_yemen_hezbollah_but_keeps_related_updates(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    fixtures = [
        _article(
            dedupe_hash="mali-1",
            title="Mali defence minister Sadio Camara says army operation secured key town",
            normalized_title="mali defence minister sadio camara says army operation secured key town",
            keywords=["mali", "sadio camara", "army", "operation", "town"],
            entities=["Sadio Camara", "Mali"],
            published_at=now - timedelta(hours=4),
            publisher="Sahel Monitor",
        ),
        _article(
            dedupe_hash="mali-2",
            title="Sadio Camara briefs Mali cabinet on follow-up security operation",
            normalized_title="sadio camara briefs mali cabinet on follow-up security operation",
            keywords=["mali", "sadio camara", "cabinet", "security", "operation"],
            entities=["Sadio Camara", "Mali"],
            published_at=now - timedelta(hours=3, minutes=30),
            publisher="Bamako Times",
        ),
        _article(
            dedupe_hash="gaza-1",
            title="Mediators push for Gaza ceasefire after overnight strikes",
            normalized_title="mediators push for gaza ceasefire after overnight strikes",
            keywords=["gaza", "ceasefire", "mediators", "strikes"],
            entities=["Gaza"],
            published_at=now - timedelta(hours=3),
            publisher="World Briefing",
        ),
        _article(
            dedupe_hash="yemen-1",
            title="Landmine blast in Yemen kills civilians near coastal road",
            normalized_title="landmine blast in yemen kills civilians near coastal road",
            keywords=["yemen", "landmine", "civilians", "coastal road"],
            entities=["Yemen"],
            published_at=now - timedelta(hours=2, minutes=45),
            publisher="Global Desk",
        ),
        _article(
            dedupe_hash="lebanon-1",
            title="Hezbollah and Lebanon officials weigh response after border exchange",
            normalized_title="hezbollah and lebanon officials weigh response after border exchange",
            keywords=["hezbollah", "lebanon", "border", "exchange"],
            entities=["Hezbollah", "Lebanon"],
            published_at=now - timedelta(hours=2, minutes=30),
            publisher="Regional Wire",
        ),
    ]
    db_session.add_all(fixtures)
    db_session.commit()

    result = cluster_new_articles(db_session, _settings())
    db_session.commit()

    assert result.attach_decisions == 1
    assert result.created_count == 4
    assert db_session.query(Cluster).count() == 4

    links = list(db_session.scalars(select(ClusterArticle).order_by(ClusterArticle.article_id.asc())).all())
    by_article = {link.article.title: link for link in links if link.article is not None}

    mali_first_cluster = by_article["Mali defence minister Sadio Camara says army operation secured key town"].cluster_id
    mali_second_cluster = by_article["Sadio Camara briefs Mali cabinet on follow-up security operation"].cluster_id
    assert mali_first_cluster == mali_second_cluster

    assert by_article["Mediators push for Gaza ceasefire after overnight strikes"].cluster_id != mali_first_cluster
    assert by_article["Landmine blast in Yemen kills civilians near coastal road"].cluster_id != mali_first_cluster
    assert by_article["Hezbollah and Lebanon officials weigh response after border exchange"].cluster_id != mali_first_cluster

    gaza_breakdown = by_article["Mediators push for Gaza ceasefire after overnight strikes"].heuristic_breakdown
    assert gaza_breakdown["decision"] == "create_new_cluster"
    assert gaza_breakdown["decision_reason"] == "no_candidate_clusters"
    assert gaza_breakdown["candidate_count"] == 0


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
