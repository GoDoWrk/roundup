from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Cluster, ClusterArticle
from app.db.session import get_db_session
from app.schemas.cluster import ClusterListResponse, StoryCluster
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

    base = select(Cluster).where(
        Cluster.status != "hidden",
        Cluster.validation_error.is_(None),
        Cluster.score >= settings.cluster_score_threshold,
        source_count_subquery >= settings.cluster_min_sources_for_api,
    )
    count_stmt = select(func.count()).select_from(Cluster).where(
        Cluster.status != "hidden",
        Cluster.validation_error.is_(None),
        Cluster.score >= settings.cluster_score_threshold,
        source_count_subquery >= settings.cluster_min_sources_for_api,
    )
    if status:
        base = base.where(Cluster.status == status)
        count_stmt = count_stmt.where(Cluster.status == status)

    total = int(db.scalar(count_stmt) or 0)

    stmt: Select[tuple[Cluster]] = (
        base.order_by(Cluster.last_updated.desc(), Cluster.id.asc()).limit(final_limit).offset(offset)
    )
    clusters = list(db.scalars(stmt).all())

    return ClusterListResponse(
        total=total,
        limit=final_limit,
        offset=offset,
        items=[build_story_cluster(db, cluster) for cluster in clusters],
    )


@router.get("/{cluster_id}", response_model=StoryCluster)
def get_cluster(cluster_id: str, db: Session = Depends(get_db_session)) -> StoryCluster:
    settings = get_settings()
    cluster = db.get(Cluster, cluster_id)
    source_count = len(cluster.source_links) if cluster is not None else 0
    if (
        cluster is None
        or cluster.status == "hidden"
        or cluster.validation_error is not None
        or cluster.score < settings.cluster_score_threshold
        or source_count < settings.cluster_min_sources_for_api
    ):
        raise HTTPException(status_code=404, detail="Cluster not found")
    return build_story_cluster(db, cluster)
