from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import Cluster, ClusterArticle
from app.db.session import get_db_session
from app.schemas.cluster import ClusterListResponse, StoryCluster
from app.services.clustering import _is_legacy_source_count_validation_error
from app.services.serialization import build_story_cluster

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("", response_model=ClusterListResponse)
def list_clusters(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> ClusterListResponse:
    settings = get_settings()
    final_limit = min(limit, settings.api_max_limit)
    source_count_subquery = (
        select(func.count())
        .select_from(ClusterArticle)
        .where(ClusterArticle.cluster_id == Cluster.id)
        .scalar_subquery()
    )
    legacy_source_count_error = f"cluster must have at least {settings.cluster_min_sources_for_api} sources"
    visible_filters = (
        Cluster.status != "hidden",
        source_count_subquery >= settings.cluster_min_sources_for_api,
        or_(Cluster.validation_error.is_(None), Cluster.validation_error == legacy_source_count_error),
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
    if (
        cluster is None
        or cluster.status == "hidden"
        or source_count < settings.cluster_min_sources_for_api
        or (
            cluster.validation_error is not None
            and not _is_legacy_source_count_validation_error(cluster.validation_error, settings)
        )
    ):
        raise HTTPException(status_code=404, detail="Cluster not found")
    return build_story_cluster(cluster)
