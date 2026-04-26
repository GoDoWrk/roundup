from datetime import datetime

from pydantic import BaseModel, Field


class ArticleResponse(BaseModel):
    article_id: int
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    published_at: datetime
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
    keywords: list[str]
    entities: list[str]
    topic: str


class ArticleDebugResponse(BaseModel):
    total: int
    items: list[ArticleDebugItem]
