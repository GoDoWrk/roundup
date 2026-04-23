from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Article, Cluster
from app.db.session import get_db_session
from app.schemas.article import ArticleDebugResponse
from app.schemas.cluster import ClusterDebugItem, ClusterDebugResponse
from app.services.serialization import article_to_debug

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/articles", response_model=ArticleDebugResponse)
def debug_articles(db: Session = Depends(get_db_session)) -> ArticleDebugResponse:
    total = int(db.scalar(select(func.count()).select_from(Article)) or 0)
    stmt: Select[tuple[Article]] = select(Article).order_by(Article.published_at.desc(), Article.id.desc())
    rows = list(db.scalars(stmt).all())
    return ArticleDebugResponse(total=total, items=[article_to_debug(article) for article in rows])


@router.get("/clusters", response_model=ClusterDebugResponse)
def debug_clusters(db: Session = Depends(get_db_session)) -> ClusterDebugResponse:
    stmt: Select[tuple[Cluster]] = select(Cluster).order_by(Cluster.last_updated.desc(), Cluster.id.asc())
    rows = list(db.scalars(stmt).all())

    items: list[ClusterDebugItem] = []
    for cluster in rows:
        items.append(
            ClusterDebugItem(
                cluster_id=cluster.id,
                status=cluster.status,
                score=cluster.score,
                source_count=len(cluster.source_links),
                validation_error=cluster.validation_error,
                headline=cluster.headline,
                summary=cluster.summary,
            )
        )

    return ClusterDebugResponse(total=len(items), items=items)
