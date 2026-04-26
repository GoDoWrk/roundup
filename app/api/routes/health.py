from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.common import HealthResponse, RuntimeSettingsResponse
from app.services.miniflux_client import MinifluxClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db_session)) -> HealthResponse:
    settings = get_settings()
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health_db_check_failed")
        db_status = "error"

    miniflux_reachable = False
    miniflux_usable = False
    if settings.miniflux_base_url.strip():
        try:
            client = MinifluxClient(
                base_url=settings.miniflux_base_url,
                api_token=settings.miniflux_api_token_resolved,
                timeout_seconds=min(settings.miniflux_timeout_seconds, 2),
            )
            miniflux_reachable = client.check_service_reachable()
            miniflux_usable = settings.has_miniflux_credentials and client.check_credentials()
        except Exception:
            logger.warning("health_miniflux_check_failed", exc_info=True)

    status = "ok"
    if db_status != "ok":
        status = "degraded"
    elif not settings.demo_mode and not miniflux_usable:
        status = "degraded"

    ingestion_active = settings.scheduler_enabled and (
        settings.demo_mode and settings.sample_data_path is not None or settings.has_miniflux_credentials
    )

    return HealthResponse(
        status=status,
        app=settings.app_name,
        db=db_status,
        miniflux_configured=settings.has_miniflux_credentials,
        miniflux_reachable=miniflux_reachable,
        miniflux_usable=miniflux_usable,
        runtime=RuntimeSettingsResponse(
            api_workers=settings.api_workers,
            inspector_worker_processes=settings.inspector_worker_processes,
            scheduler_enabled=settings.scheduler_enabled,
            scheduler_interval_seconds=settings.scheduler_interval_seconds,
            ingestion_concurrency=settings.ingestion_concurrency,
            summarization_concurrency=settings.summarization_concurrency,
            clustering_batch_size=settings.clustering_batch_size,
            clustering_concurrency=settings.clustering_concurrency,
            ingestion_active=ingestion_active,
        ),
        timestamp=datetime.now(timezone.utc),
    )
