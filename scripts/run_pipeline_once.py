from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.models import Article, Cluster, ClusterArticle
from app.db.session import SessionLocal
from app.services.normalizer import canonicalize_url, normalize_whitespace
from app.services.pipeline import run_pipeline
from app.services.sample_data import load_sample_entries

logger = logging.getLogger(__name__)


def _collect_sample_canonical_urls(sample_path: Path) -> set[str]:
    entries = load_sample_entries(sample_path)
    canonical_urls: set[str] = set()
    for entry in entries:
        raw_url = normalize_whitespace(str(entry.get("url") or ""))
        if not raw_url:
            continue
        canonical = canonicalize_url(raw_url)
        if canonical:
            canonical_urls.add(canonical)
    return canonical_urls


def _prune_orphan_clusters(session: Session) -> int:
    orphan_cluster_ids = list(
        session.scalars(
            select(Cluster.id)
            .outerjoin(ClusterArticle, ClusterArticle.cluster_id == Cluster.id)
            .group_by(Cluster.id)
            .having(func.count(ClusterArticle.id) == 0)
        ).all()
    )
    if not orphan_cluster_ids:
        return 0

    deleted = (
        session.query(Cluster)
        .filter(Cluster.id.in_(orphan_cluster_ids))
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def reset_sample_mode_state_if_needed(session: Session, settings: Settings) -> None:
    sample_path = settings.sample_data_path
    if sample_path is None or settings.has_miniflux_credentials:
        return

    sample_urls = _collect_sample_canonical_urls(sample_path)
    if not sample_urls:
        logger.info("sample_mode_reset_skipped reason=no_sample_urls path=%s", sample_path)
        return

    article_ids = list(
        session.scalars(select(Article.id).where(Article.canonical_url.in_(sample_urls))).all()
    )
    deleted_articles = 0
    if article_ids:
        deleted_articles = (
            session.query(Article)
            .filter(Article.id.in_(article_ids))
            .delete(synchronize_session=False)
        )

    pruned_clusters = _prune_orphan_clusters(session)
    session.flush()
    logger.info(
        "sample_mode_reset_complete path=%s sample_urls=%s deleted_articles=%s pruned_clusters=%s",
        sample_path,
        len(sample_urls),
        deleted_articles,
        pruned_clusters,
    )


def main() -> None:
    configure_logging()
    settings = get_settings()
    run_startup_checks("worker", settings=settings)
    run_id = uuid4().hex[:8]
    with SessionLocal() as session:
        reset_sample_mode_state_if_needed(session, settings)
        result = run_pipeline(session, settings, run_id=run_id)
    print(
        "run_id={0} source={1} fetched={2} ingested={3} deduplicated={4} malformed={5} clusters_created={6} clusters_updated={7}".format(
            run_id,
            result.ingestion_source,
            result.fetched,
            result.ingested,
            result.deduplicated,
            result.malformed,
            result.clusters_created,
            result.clusters_updated,
        )
    )


if __name__ == "__main__":
    main()
