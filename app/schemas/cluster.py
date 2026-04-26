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
    image_url: str | None = None


ClusterStatus = Literal["emerging", "active", "stale"]


class StoryCluster(BaseModel):
    cluster_id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    what_changed: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    key_facts: list[str]
    timeline: list[TimelineEvent]
    timeline_events: list[TimelineEvent]
    sources: list[SourceReference]
    source_count: int
    primary_image_url: str | None
    thumbnail_urls: list[str]
    topic: str
    region: str | None
    story_type: str
    first_seen: datetime
    last_updated: datetime
    is_developing: bool
    is_breaking: bool
    confidence_score: float
    related_cluster_ids: list[str]
    score: float
    status: ClusterStatus


class ClusterListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StoryCluster]


class ClusterDebugThresholds(BaseModel):
    score_threshold: float
    title_signal_threshold: float
    entity_overlap_threshold: int
    keyword_overlap_threshold: int
    topic_semantic_score_threshold: float
    attach_override_title_similarity_threshold: float
    attach_override_time_proximity_threshold: float
    min_sources_for_api: int


class ClusterDebugScoreBreakdown(BaseModel):
    average_similarity_score: float
    average_title_similarity: float
    average_entity_jaccard: float
    average_keyword_jaccard: float
    average_semantic_score: float
    average_time_proximity: float
    score_formula: str
    semantic_formula: str


class ClusterDebugJoinDecision(BaseModel):
    article_id: int
    article_title: str
    publisher: str
    decision: str
    reason: str
    selected_cluster_id: str | None
    selected_score: float
    title_similarity: float
    entity_jaccard: float
    keyword_jaccard: float
    semantic_score: float
    entity_overlap: int
    keyword_overlap: int
    topic_match: bool
    time_proximity: float
    signal_gate_passed: bool
    signal_reasons: list[str]
    warnings: list[str]


class ClusterDebugExplanation(BaseModel):
    grouping_reason: str
    thresholds: ClusterDebugThresholds
    threshold_results: dict[str, bool]
    top_shared_entities: list[str]
    top_shared_keywords: list[str]
    score_breakdown: ClusterDebugScoreBreakdown
    decision_counts: dict[str, int]
    recent_join_decisions: list[ClusterDebugJoinDecision]
    warnings: list[str]


class ClusterDebugItem(BaseModel):
    cluster_id: str
    status: str
    score: float
    topic: str
    source_count: int
    visibility_threshold: int
    promotion_eligible: bool
    promoted_at: datetime | None
    previous_status: str | None
    promotion_reason: str | None
    promotion_explanation: str | None
    promotion_blockers: list[str]
    validation_error: str | None
    headline: str
    summary: str
    debug_explanation: ClusterDebugExplanation


class ClusterDebugResponse(BaseModel):
    total: int
    items: list[ClusterDebugItem]
