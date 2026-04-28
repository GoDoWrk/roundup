from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Cluster, ClusterArticle
from app.db.session import get_db_session
from app.schemas.cluster import (
    ClusterListResponse,
    HomepageClusterSections,
    HomepageClusterThresholds,
    HomepageClustersResponse,
    HomepagePipelineStatus,
    StoryCluster,
)
from app.services.clustering import _is_legacy_source_count_validation_error
from app.services.metrics import (
    count_active_sources,
    count_articles_pending_clustering,
    count_summaries_pending,
    get_or_create_pipeline_stats,
)
from app.services.serialization import build_story_cluster

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


def _source_count_subquery():
    return (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )


def _legacy_source_count_error(settings) -> str:
    return f"cluster must have at least {settings.cluster_min_sources_for_api} sources"


def _valid_or_legacy_source_count_filter(settings):
    legacy_source_count_error = _legacy_source_count_error(settings)
    return or_(Cluster.validation_error.is_(None), Cluster.validation_error == legacy_source_count_error)


def _load_section_clusters(
    db: Session,
    *,
    filters: tuple,
    order_by: tuple,
    limit: int,
) -> list[Cluster]:
    stmt: Select[tuple[Cluster]] = (
        select(Cluster)
        .options(
            selectinload(Cluster.source_links).selectinload(ClusterArticle.article),
            selectinload(Cluster.timeline_events),
        )
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
    )
    return list(db.scalars(stmt).unique().all())


def _visibility_label(cluster: Cluster, fallback: str) -> str:
    source_count = len(cluster.source_links)
    if source_count == 1:
        return "Single source"
    if cluster.status == "hidden":
        return "Developing candidate"
    return fallback


def _is_detail_visible(cluster: Cluster, source_count: int, settings) -> bool:
    if cluster.validation_error is not None and not _is_legacy_source_count_validation_error(cluster.validation_error, settings):
        return False

    if cluster.status == "hidden":
        return bool(settings.cluster_show_just_in_single_source and source_count >= 1)

    if cluster.status != "hidden" and source_count >= settings.cluster_min_sources_for_developing_stories:
        return True

    return False


@router.get("", response_model=ClusterListResponse)
def list_clusters(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> ClusterListResponse:
    settings = get_settings()
    final_limit = min(limit, settings.api_max_limit)
    source_count_subquery = _source_count_subquery()
    visible_filters = (
        Cluster.status != "hidden",
        source_count_subquery >= settings.cluster_min_sources_for_api,
        _valid_or_legacy_source_count_filter(settings),
    )
    base = (
        select(Cluster)
        .options(
            selectinload(Cluster.source_links).selectinload(ClusterArticle.article),
            selectinload(Cluster.timeline_events),
        )
        .where(*visible_filters)
    )
    count_stmt = select(func.count()).select_from(Cluster).where(*visible_filters)
    if status:
        base = base.where(Cluster.status == status)
        count_stmt = count_stmt.where(Cluster.status == status)

    total = int(db.scalar(count_stmt) or 0)

    stmt: Select[tuple[Cluster]] = (
        base.order_by(Cluster.last_updated.desc(), Cluster.id.asc()).limit(final_limit).offset(offset)
    )
    clusters = list(db.scalars(stmt).unique().all())

    return ClusterListResponse(
        total=total,
        limit=final_limit,
        offset=offset,
        items=[build_story_cluster(cluster) for cluster in clusters],
    )


@router.get("/homepage", response_model=HomepageClustersResponse)
def homepage_clusters(db: Session = Depends(get_db_session)) -> HomepageClustersResponse:
    settings = get_settings()
    source_count = _source_count_subquery()
    valid_or_legacy_source_count = _valid_or_legacy_source_count_filter(settings)

    public_filters = (
        Cluster.status != "hidden",
        source_count >= settings.cluster_min_sources_for_top_stories,
        valid_or_legacy_source_count,
    )
    top_rows = _load_section_clusters(
        db,
        filters=public_filters,
        order_by=(Cluster.score.desc(), Cluster.last_updated.desc(), Cluster.id.asc()),
        limit=settings.cluster_homepage_top_limit,
    )
    top_ids = {cluster.id for cluster in top_rows}

    developing_rows = [
        cluster
        for cluster in _load_section_clusters(
            db,
            filters=(
                Cluster.status != "hidden",
                source_count >= settings.cluster_min_sources_for_developing_stories,
                valid_or_legacy_source_count,
            ),
            order_by=(Cluster.last_updated.desc(), Cluster.score.desc(), Cluster.id.asc()),
            limit=settings.cluster_homepage_developing_limit + len(top_ids),
        )
        if cluster.id not in top_ids
    ][: settings.cluster_homepage_developing_limit]
    used_ids = top_ids.union(cluster.id for cluster in developing_rows)

    just_in_rows = [
        cluster
        for cluster in _load_section_clusters(
            db,
            filters=(
                source_count >= (1 if settings.cluster_show_just_in_single_source else settings.cluster_min_sources_for_developing_stories),
                valid_or_legacy_source_count,
            ),
            order_by=(Cluster.last_updated.desc(), Cluster.id.asc()),
            limit=settings.cluster_homepage_just_in_limit + len(used_ids),
        )
        if cluster.id not in used_ids
    ][: settings.cluster_homepage_just_in_limit]

    candidate_min_sources = 1 if settings.cluster_show_just_in_single_source else 2
    visible_clusters = int(
        db.scalar(select(func.count()).select_from(Cluster).where(*public_filters)) or 0
    )
    candidate_clusters = int(
        db.scalar(
            select(func.count())
            .select_from(Cluster)
            .where(
                source_count >= candidate_min_sources,
                valid_or_legacy_source_count,
                or_(
                    Cluster.status == "hidden",
                    source_count < settings.cluster_min_sources_for_top_stories,
                ),
            )
        )
        or 0
    )
    stats = get_or_create_pipeline_stats(db)

    return HomepageClustersResponse(
        sections=HomepageClusterSections(
            top_stories=[
                build_story_cluster(cluster, visibility="top_story", visibility_label="Top story")
                for cluster in top_rows
            ],
            developing_stories=[
                build_story_cluster(cluster, visibility="developing", visibility_label="Developing")
                for cluster in developing_rows
            ],
            just_in=[
                build_story_cluster(
                    cluster,
                    visibility="candidate" if cluster.status == "hidden" or len(cluster.source_links) == 1 else "public",
                    visibility_label=_visibility_label(cluster, "Latest update"),
                )
                for cluster in just_in_rows
            ],
        ),
        status=HomepagePipelineStatus(
            visible_clusters=visible_clusters,
            candidate_clusters=candidate_clusters,
            articles_fetched_latest_run=stats.latest_articles_fetched,
            articles_stored_latest_run=stats.latest_articles_stored,
            duplicate_articles_skipped_latest_run=stats.latest_duplicate_articles_skipped,
            failed_source_count=stats.latest_failed_source_count,
            active_sources=count_active_sources(db),
            last_ingestion=stats.last_ingest_time,
            articles_pending=count_articles_pending_clustering(db),
            summaries_pending=count_summaries_pending(db),
        ),
        thresholds=HomepageClusterThresholds(
            min_sources_for_top_stories=settings.cluster_min_sources_for_top_stories,
            min_sources_for_developing_stories=settings.cluster_min_sources_for_developing_stories,
            show_just_in_single_source=settings.cluster_show_just_in_single_source,
            max_top_stories=settings.cluster_homepage_top_limit,
            max_developing_stories=settings.cluster_homepage_developing_limit,
            max_just_in=settings.cluster_homepage_just_in_limit,
        ),
    )


@router.get("/{cluster_id}", response_model=StoryCluster)
def get_cluster(cluster_id: str, db: Session = Depends(get_db_session)) -> StoryCluster:
    settings = get_settings()
    cluster = db.get(
        Cluster,
        cluster_id,
        options=[
            selectinload(Cluster.source_links).selectinload(ClusterArticle.article),
            selectinload(Cluster.timeline_events),
        ],
    )
    source_count = len(cluster.source_links) if cluster is not None else 0
    if cluster is None or not _is_detail_visible(cluster, source_count, settings):
        raise HTTPException(status_code=404, detail="Cluster not found")
    if cluster.status == "hidden":
        return build_story_cluster(cluster, visibility="candidate", visibility_label=_visibility_label(cluster, "Latest update"))
    return build_story_cluster(cluster)
