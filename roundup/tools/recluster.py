from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.db.models import Article, Cluster, ClusterArticle, ClusterTimelineEvent
from app.db.session import SessionLocal
from app.services.clustering import cluster_new_articles


def _source_count_subquery():
    return (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )


def _delete_orphan_clusters(session) -> None:
    source_count = _source_count_subquery()
    orphan_ids = list(session.scalars(select(Cluster.id).where(source_count == 0)).all())
    if not orphan_ids:
        return
    session.execute(delete(ClusterTimelineEvent).where(ClusterTimelineEvent.cluster_id.in_(orphan_ids)))
    session.execute(delete(Cluster).where(Cluster.id.in_(orphan_ids)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear and rebuild clusters for a recent article window.")
    parser.add_argument("--since-hours", type=int, default=48, help="Recluster articles published within this many hours.")
    args = parser.parse_args()

    if args.since_hours <= 0:
        raise SystemExit("--since-hours must be greater than 0")

    settings = get_settings()
    threshold = datetime.now(timezone.utc) - timedelta(hours=args.since_hours)

    with SessionLocal() as session:
        article_ids = list(
            session.scalars(
                select(Article.id).where(Article.published_at >= threshold).order_by(Article.published_at.asc(), Article.id.asc())
            ).all()
        )
        processed = len(article_ids)
        if article_ids:
            cluster_ids = list(
                session.scalars(select(ClusterArticle.cluster_id).where(ClusterArticle.article_id.in_(article_ids))).all()
            )
            session.execute(delete(ClusterArticle).where(ClusterArticle.article_id.in_(article_ids)))
            if cluster_ids:
                session.execute(delete(ClusterTimelineEvent).where(ClusterTimelineEvent.cluster_id.in_(cluster_ids)))
            _delete_orphan_clusters(session)
            session.flush()

        result = cluster_new_articles(session, settings, article_ids=article_ids)
        session.flush()

        rebuilt_links = list(
            session.scalars(
                select(ClusterArticle)
                .join(Article, Article.id == ClusterArticle.article_id)
                .where(Article.id.in_(article_ids))
            ).all()
        )
        reason_counts: Counter[str] = Counter()
        quarantined = 0
        accepted = 0
        for link in rebuilt_links:
            breakdown = link.heuristic_breakdown or {}
            status = breakdown.get("membership_rejection_status")
            if status and status != "candidate_needs_more_sources":
                quarantined += 1
                reason_counts[str(status)] += 1
            else:
                accepted += 1

        session.commit()

    print(
        "\n".join(
            [
                f"articles_processed={processed}",
                f"clusters_created={result.created_count}",
                f"articles_accepted={accepted}",
                f"articles_quarantined={quarantined}",
                "rejection_reason_counts="
                + ",".join(f"{reason}:{count}" for reason, count in sorted(reason_counts.items())),
            ]
        )
    )


if __name__ == "__main__":
    main()
