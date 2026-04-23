from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.common import HealthResponse
from app.services.miniflux_client import MinifluxClient

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db_session)) -> HealthResponse:
    settings = get_settings()
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    miniflux_reachable = False
    miniflux_usable = False
    if settings.miniflux_base_url.strip():
        client = MinifluxClient(
            base_url=settings.miniflux_base_url,
            api_token=settings.miniflux_api_token_resolved,
            timeout_seconds=min(settings.miniflux_timeout_seconds, 2),
        )
        miniflux_reachable = client.check_service_reachable()
        miniflux_usable = settings.has_miniflux_credentials and client.check_credentials()

    status = "ok"
    if db_status != "ok":
        status = "degraded"
    elif not settings.demo_mode and not miniflux_usable:
        status = "degraded"

    return HealthResponse(
        status=status,
        app=settings.app_name,
        db=db_status,
        miniflux_configured=settings.has_miniflux_credentials,
        miniflux_reachable=miniflux_reachable,
        miniflux_usable=miniflux_usable,
        timestamp=datetime.now(timezone.utc),
    )
