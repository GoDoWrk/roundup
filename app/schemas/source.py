from datetime import datetime

from pydantic import BaseModel, Field


class SourceHealthItem(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    provider_label: str = Field(min_length=1)
    feed_url: str | None = None
    group: str | None = None
    enabled: bool | None = None
    last_fetched_at: datetime | None = None
    recent_article_count: int
    error_status: str | None = None
    error_message: str | None = None


class SourceListResponse(BaseModel):
    provider: str
    metadata_available: bool
    status: str
    message: str
    total: int
    items: list[SourceHealthItem]
