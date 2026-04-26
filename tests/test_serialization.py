from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Article, Cluster, ClusterArticle
from app.services.serialization import build_story_cluster


def _article(idx: int, now: datetime, image_url: str | None) -> Article:
    return Article(
        id=idx,
        external_id=None,
        title=f"Transit update {idx}",
        url=f"https://example.com/{idx}",
        canonical_url=f"https://example.com/{idx}",
        publisher=f"Publisher {idx}",
        published_at=now + timedelta(minutes=idx),
        content_text="Body",
        image_url=image_url,
        raw_payload={"id": idx},
        normalized_title=f"transit update {idx}",
        keywords=["transit", "update"],
        entities=["City Council"],
        dedupe_hash=f"hash-{idx}",
    )


def _cluster(now: datetime) -> Cluster:
    return Cluster(
        id="cluster-1",
        headline="Transit Plan Advances",
        summary="Multiple outlets covered the transit plan update with consistent facts.",
        what_changed="Coverage added new budget details.",
        why_it_matters="The change affects service planning.",
        first_seen=now,
        last_updated=now,
        score=0.8,
        status="active",
        normalized_headline="transit plan advances",
        keywords=["transit", "plan"],
        entities=["City Council"],
    )


def test_build_story_cluster_selects_newest_image_and_deduplicates_thumbnails() -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster(now)
    older = _article(1, now, "https://cdn.example.com/older.jpg")
    newest = _article(3, now, "https://cdn.example.com/newest.jpg#tracking")
    duplicate = _article(2, now, "https://cdn.example.com/older.jpg")

    cluster.source_links = [
        ClusterArticle(article=older, similarity_score=0.99),
        ClusterArticle(article=duplicate, similarity_score=0.5),
        ClusterArticle(article=newest, similarity_score=0.7),
    ]

    payload = build_story_cluster(cluster)

    assert payload.primary_image_url == "https://cdn.example.com/newest.jpg"
    assert payload.thumbnail_urls == [
        "https://cdn.example.com/newest.jpg",
        "https://cdn.example.com/older.jpg",
    ]


def test_build_story_cluster_uses_similarity_as_newest_tiebreaker_and_falls_back_empty() -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster(now)
    low_similarity = _article(1, now, "https://cdn.example.com/low.jpg")
    high_similarity = _article(2, now, "https://cdn.example.com/high.jpg")
    low_similarity.published_at = now
    high_similarity.published_at = now

    cluster.source_links = [
        ClusterArticle(article=low_similarity, similarity_score=0.1),
        ClusterArticle(article=high_similarity, similarity_score=0.8),
    ]

    payload = build_story_cluster(cluster)
    assert payload.primary_image_url == "https://cdn.example.com/high.jpg"

    empty_cluster = _cluster(now)
    empty_cluster.source_links = [ClusterArticle(article=_article(3, now, None), similarity_score=1.0)]
    empty_payload = build_story_cluster(empty_cluster)
    assert empty_payload.primary_image_url is None
    assert empty_payload.thumbnail_urls == []


def test_build_story_cluster_falls_back_to_raw_payload_image_when_column_is_empty() -> None:
    now = datetime.now(timezone.utc)
    cluster = _cluster(now)
    article = _article(1, now, None)
    article.raw_payload = {
        "enclosures": [
            {
                "url": "https://i.guim.co.uk/img/media/example/master/2336.jpg?width=700",
                "mime_type": "application/octet-stream",
            }
        ]
    }
    cluster.source_links = [ClusterArticle(article=article, similarity_score=0.8)]

    payload = build_story_cluster(cluster)

    assert payload.primary_image_url == "https://i.guim.co.uk/img/media/example/master/2336.jpg?width=700"
    assert payload.sources[0].image_url == "https://i.guim.co.uk/img/media/example/master/2336.jpg?width=700"
