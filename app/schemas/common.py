from datetime import datetime

from pydantic import BaseModel


class RuntimeSettingsResponse(BaseModel):
    api_workers: int
    inspector_worker_processes: int
    scheduler_enabled: bool
    scheduler_interval_seconds: int
    ingestion_concurrency: int
    summarization_concurrency: int
    clustering_batch_size: int
    clustering_concurrency: int
    ingestion_active: bool


class HealthResponse(BaseModel):
    status: str
    app: str
    db: str
    miniflux_configured: bool
    miniflux_reachable: bool
    miniflux_usable: bool
    runtime: RuntimeSettingsResponse
    timestamp: datetime


class ApiIndexResponse(BaseModel):
    message: str
    docs_url: str
    endpoints: dict[str, str]
