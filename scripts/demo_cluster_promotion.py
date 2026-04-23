from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import Article, Cluster, ClusterArticle
from app.db.session import SessionLocal
from app.services.clustering import cluster_new_articles


def _demo_article(
    dedupe_hash: str,
    *,
    title: str,
    url: str,
    published_at: datetime,
    publisher: str,
) -> Article:
    return Article(
        external_id=None,
        title=title,
        url=url,
        canonical_url=url,
        publisher=publisher,
        published_at=published_at,
        content_text=title,
        raw_payload={"title": title, "demo": True},
        normalized_title="roundup demo zeta42 project update",
        keywords=["roundup", "demo", "zeta42", "project", "update", "funding", "timeline"],
        entities=["Zeta42 Program", "City Council"],
        dedupe_hash=dedupe_hash,
    )


def _find_cluster_for_url(session, canonical_url: str) -> Cluster | None:
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .join(ClusterArticle, ClusterArticle.cluster_id == Cluster.id)
        .join(Article, Article.id == ClusterArticle.article_id)
        .where(Article.canonical_url == canonical_url)
    )
    return session.scalars(stmt).first()


def _source_count(session, cluster_id: str) -> int:
    return int(
        session.scalar(select(func.count()).select_from(ClusterArticle).where(ClusterArticle.cluster_id == cluster_id))
        or 0
    )


def main() -> None:
    configure_logging()
    settings = get_settings()
    now = datetime.now(timezone.utc)

    entries = [
        _demo_article(
            "promo-zeta42-1",
            title="Roundup Demo Zeta42 Project Update: Funding Approved",
            url="https://demo.roundup.local/transit-expansion-1",
            published_at=now - timedelta(hours=3),
            publisher="Demo Wire One",
        ),
        _demo_article(
            "promo-zeta42-2",
            title="Roundup Demo Zeta42 Project Update: Funding Plan Expanded",
            url="https://demo.roundup.local/transit-expansion-2",
            published_at=now - timedelta(hours=2),
            publisher="Demo Wire Two",
        ),
        _demo_article(
            "promo-zeta42-3",
            title="Roundup Demo Zeta42 Project Update: Implementation Timeline Published",
            url="https://demo.roundup.local/transit-expansion-3",
            published_at=now - timedelta(hours=1),
            publisher="Demo Wire Three",
        ),
    ]

    canonical_urls = [item.canonical_url for item in entries]

    with SessionLocal() as session:
        # Clean up prior demo rows for deterministic reruns.
        demo_articles = session.scalars(select(Article).where(Article.canonical_url.in_(canonical_urls))).all()
        demo_article_ids = [article.id for article in demo_articles]
        if demo_article_ids:
            session.query(Article).filter(Article.id.in_(demo_article_ids)).delete(synchronize_session=False)
            session.flush()

        # Phase 1: hidden cluster with one source.
        session.add(entries[0])
        session.flush()
        cluster_new_articles(session, settings)
        session.commit()

        phase1_cluster = _find_cluster_for_url(session, entries[0].canonical_url)
        if phase1_cluster is None:
            raise RuntimeError("Failed to create initial demo cluster.")

        print(
            "phase=1 cluster_id={0} status={1} source_count={2} first_seen={3} promoted_at={4} validation_error={5}".format(
                phase1_cluster.id,
                phase1_cluster.status,
                _source_count(session, phase1_cluster.id),
                phase1_cluster.first_seen.isoformat(),
                phase1_cluster.promoted_at.isoformat() if phase1_cluster.promoted_at else "null",
                phase1_cluster.validation_error or "none",
            )
        )
        if _source_count(session, phase1_cluster.id) != 1:
            raise RuntimeError("Demo cluster did not isolate to a single source in phase 1.")

        # Phase 2: still hidden at two sources (threshold expected 3).
        session.add(entries[1])
        session.flush()
        cluster_new_articles(session, settings)
        session.commit()

        phase2_cluster = session.get(Cluster, phase1_cluster.id)
        if phase2_cluster is None:
            raise RuntimeError("Cluster continuity failed between phase 1 and phase 2.")

        print(
            "phase=2 cluster_id={0} status={1} source_count={2} first_seen={3} promoted_at={4} validation_error={5}".format(
                phase2_cluster.id,
                phase2_cluster.status,
                _source_count(session, phase2_cluster.id),
                phase2_cluster.first_seen.isoformat(),
                phase2_cluster.promoted_at.isoformat() if phase2_cluster.promoted_at else "null",
                phase2_cluster.validation_error or "none",
            )
        )
        if _source_count(session, phase2_cluster.id) != 2:
            raise RuntimeError("Demo cluster did not retain continuity with two sources in phase 2.")

        # Phase 3: promotion to active with three sources.
        session.add(entries[2])
        session.flush()
        cluster_new_articles(session, settings)
        session.commit()

        phase3_cluster = session.get(Cluster, phase1_cluster.id)
        if phase3_cluster is None:
            raise RuntimeError("Cluster continuity failed between phase 2 and phase 3.")

        print(
            "phase=3 cluster_id={0} status={1} source_count={2} first_seen={3} promoted_at={4} previous_status={5} promotion_reason={6}".format(
                phase3_cluster.id,
                phase3_cluster.status,
                _source_count(session, phase3_cluster.id),
                phase3_cluster.first_seen.isoformat(),
                phase3_cluster.promoted_at.isoformat() if phase3_cluster.promoted_at else "null",
                phase3_cluster.previous_status or "null",
                phase3_cluster.promotion_reason or "null",
            )
        )
        if _source_count(session, phase3_cluster.id) != 3:
            raise RuntimeError("Demo cluster did not retain continuity with three sources in phase 3.")


if __name__ == "__main__":
    main()
