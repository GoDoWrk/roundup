from datetime import datetime

from pydantic import BaseModel, Field


class ArticleResponse(BaseModel):
    article_id: int
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    published_at: datetime
    image_url: str | None = None
    topic: str


class ArticleListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ArticleResponse]


class ArticleDebugItem(BaseModel):
    article_id: int
    dedupe_hash: str
    title: str
    normalized_title: str
    publisher: str
    published_at: datetime
    image_url: str | None = None
    keywords: list[str]
    entities: list[str]
    topic: str
    quality_action: str
    quality_reasons: list[str]
    source_trust: str
    source_priority: str
    allow_service_content: bool
    promote_to_home: bool
    source_category: str
    content_class: str
    primary_entities: list[str] = Field(default_factory=list)
    secondary_entities: list[str] = Field(default_factory=list)


class ArticleDebugResponse(BaseModel):
    total: int
    items: list[ArticleDebugItem]
