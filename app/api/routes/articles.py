from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Article
from app.db.session import get_db_session
from app.schemas.article import ArticleListResponse
from app.services.serialization import article_to_response

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=ArticleListResponse)
def list_articles(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> ArticleListResponse:
    settings = get_settings()
    final_limit = min(limit, settings.api_max_limit)

    total = db.scalar(select(func.count()).select_from(Article)) or 0
    stmt: Select[tuple[Article]] = select(Article).order_by(Article.published_at.desc(), Article.id.desc()).limit(final_limit).offset(offset)
    rows = list(db.scalars(stmt).all())

    return ArticleListResponse(
        total=int(total),
        limit=final_limit,
        offset=offset,
        items=[article_to_response(item) for item in rows],
    )
