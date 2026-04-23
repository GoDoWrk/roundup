from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str
    db: str
    miniflux_configured: bool
    timestamp: datetime
