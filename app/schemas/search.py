from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SearchResultType = Literal["cluster", "update", "source"]


class SearchCounts(BaseModel):
    all: int
    clusters: int
    updates: int
    sources: int


class SearchResult(BaseModel):
    id: str = Field(min_length=1)
    type: SearchResultType
    cluster_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    topic: str
    thumbnail_url: str | None = None
    source_name: str | None = None
    source_count: int
    update_count: int
    last_updated: datetime
    article_url: str | None = None
    published_at: datetime | None = None
    matched_field: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    limit: int
    counts: SearchCounts
    items: list[SearchResult]
