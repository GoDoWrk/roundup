from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.services.enrichment import build_what_changed
from app.services.clustering import cluster_new_articles
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
