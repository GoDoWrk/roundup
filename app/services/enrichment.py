from __future__ import annotations

from datetime import datetime

from app.db.models import Article


def _fallback_text(prefix: str, cluster_id: str) -> str:
    return f"{prefix} for cluster {cluster_id}."


def build_headline(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("No headline available", cluster_id)
    latest = sorted(articles, key=lambda a: (a.published_at, a.id), reverse=True)[0]
    title = (latest.title or "").strip()
    return title or _fallback_text("No headline available", cluster_id)


def build_summary(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("No summary available", cluster_id)
    publishers = sorted({a.publisher for a in articles if a.publisher})
    keywords: list[str] = []
    for article in articles:
        for keyword in article.keywords:
            if keyword not in keywords:
                keywords.append(keyword)
    publisher_text = ", ".join(publishers[:3]) if publishers else "multiple sources"
    keyword_text = ", ".join(keywords[:5]) if keywords else "developing details"
    summary = f"{len(articles)} related reports from {publisher_text} focus on {keyword_text}."
    return summary if summary.strip() else _fallback_text("No summary available", cluster_id)


def build_what_changed(cluster_id: str, articles: list[Article]) -> str:
    if len(articles) < 2:
        return "Coverage has started and is still forming with initial reporting."
    ordered = sorted(articles, key=lambda a: (a.published_at, a.id))
    first = ordered[0]
    latest = ordered[-1]
    hours = max(0, int((latest.published_at - first.published_at).total_seconds() // 3600))
    sentence = (
        f"Coverage expanded from {first.publisher} to {latest.publisher} over {hours} hours as new details were published."
    )
    return sentence if sentence.strip() else _fallback_text("No change summary available", cluster_id)


def build_why_it_matters(cluster_id: str, articles: list[Article]) -> str:
    if not articles:
        return _fallback_text("No impact statement available", cluster_id)
    earliest = min(a.published_at for a in articles)
    latest = max(a.published_at for a in articles)
    span_hours = max(0, int((latest - earliest).total_seconds() // 3600))
    text = (
        f"This story matters because {len(articles)} sources are tracking it across a {span_hours}-hour window, signaling ongoing relevance."
    )
    return text if text.strip() else _fallback_text("No impact statement available", cluster_id)


def build_timeline_event_text(article: Article) -> str:
    title = (article.title or "").strip()
    if title:
        return f"{article.publisher} reported: {title}"
    return f"{article.publisher} published an update."


def build_status(
    source_count: int,
    last_updated: datetime,
    now: datetime,
    stale_hours: int,
    emerging_hours: int,
    emerging_source_count: int,
) -> str:
    hours_since_update = (now - last_updated).total_seconds() / 3600
    if hours_since_update >= stale_hours:
        return "stale"
    if source_count < emerging_source_count and hours_since_update <= emerging_hours:
        return "emerging"
    return "active"
