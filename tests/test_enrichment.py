from datetime import datetime, timezone

from app.db.models import Article
from app.services.enrichment import build_key_facts


def _article(index: int) -> Article:
    return Article(
        external_id=None,
        title=f"Israel security update {index}",
        url=f"https://example.com/{index}",
        canonical_url=f"https://example.com/{index}",
        publisher=f"Publisher {index}",
        published_at=datetime(2026, 4, 26, 12, index, tzinfo=timezone.utc),
        content_text="Body",
        raw_payload={},
        normalized_title=f"israel security update {index}",
        keywords=["blank", "com", "href", "https", "security"],
        entities=["Israel"],
        dedupe_hash=f"enrichment-{index}",
    )


def test_key_facts_filter_html_feed_artifact_keywords() -> None:
    facts = build_key_facts("cluster-1", [_article(1), _article(2)])

    joined = " ".join(facts).lower()
    assert "recurring themes include security" in joined
    assert "blank" not in joined
    assert "href" not in joined
    assert "https" not in joined
