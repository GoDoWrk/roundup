from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    timestamp: datetime
    event: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_title: str = Field(min_length=1)


class SourceReference(BaseModel):
    article_id: int
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    published_at: datetime


ClusterStatus = Literal["emerging", "active", "stale"]


class StoryCluster(BaseModel):
    cluster_id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    what_changed: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    timeline: list[TimelineEvent]
    sources: list[SourceReference]
    first_seen: datetime
    last_updated: datetime
    score: float
    status: ClusterStatus


class ClusterListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StoryCluster]


class ClusterDebugItem(BaseModel):
    cluster_id: str
    status: str
    score: float
    source_count: int
    validation_error: str | None
    headline: str
    summary: str


class ClusterDebugResponse(BaseModel):
    total: int
    items: list[ClusterDebugItem]
