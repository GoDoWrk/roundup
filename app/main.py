from __future__ import annotations

from fastapi import Depends, FastAPI, Response
from sqlalchemy.orm import Session

from app.api.routes.articles import router as articles_router
from app.api.routes.clusters import router as clusters_router
from app.api.routes.debug import router as debug_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.session import get_db_session
from app.schemas.common import ApiIndexResponse
from app.services.metrics import metrics_as_prometheus_text

configure_logging()

app = FastAPI(title="Roundup", version="0.1.0")

app.include_router(health_router)
app.include_router(articles_router)
app.include_router(clusters_router)
app.include_router(debug_router)


@app.get("/", response_model=ApiIndexResponse, tags=["meta"])
def api_index() -> ApiIndexResponse:
    settings = get_settings()
    return ApiIndexResponse(
        message=f"{settings.app_name} API is running. Start with these endpoints.",
        docs_url="/docs",
        endpoints={
            "health": "/health",
            "clusters": "/api/clusters",
            "debug_clusters": "/debug/clusters",
            "metrics": "/metrics",
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    run_startup_checks("api")


@app.get("/metrics", include_in_schema=False)
def get_metrics(db: Session = Depends(get_db_session)) -> Response:
    payload = metrics_as_prometheus_text(db)
    return Response(content=payload, media_type="text/plain; version=0.0.4")
