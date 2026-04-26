from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.source import SourceListResponse
from app.services.sources import build_source_list

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=SourceListResponse)
def list_sources(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SourceListResponse:
    return build_source_list(db, settings)
