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


ClusterStatus = Literal["emerging", "active", "stale", "hidden"]


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
    visibility: Literal["top_story", "developing", "candidate", "public"] = "public"
    visibility_label: str = "Confirmed"
    is_single_source: bool = False


class ClusterListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StoryCluster]


class HomepageClusterThresholds(BaseModel):
    min_sources_for_top_stories: int
    min_sources_for_developing_stories: int
    show_just_in_single_source: bool
    max_top_stories: int
    max_developing_stories: int
    max_just_in: int


class HomepagePipelineStatus(BaseModel):
    visible_clusters: int
    candidate_clusters: int
    articles_fetched_latest_run: int
    articles_stored_latest_run: int
    duplicate_articles_skipped_latest_run: int
    failed_source_count: int
    active_sources: int
    last_ingestion: datetime | None
    articles_pending: int
    summaries_pending: int


class HomepageClusterSections(BaseModel):
    top_stories: list[StoryCluster]
    developing_stories: list[StoryCluster]
    just_in: list[StoryCluster]


class HomepageClustersResponse(BaseModel):
    sections: HomepageClusterSections
    status: HomepagePipelineStatus
    thresholds: HomepageClusterThresholds


class ClusterDebugThresholds(BaseModel):
    score_threshold: float
    title_signal_threshold: float
    entity_overlap_threshold: int
    keyword_overlap_threshold: int
    min_sources_for_api: int
    min_sources_for_top_stories: int
    min_sources_for_developing_stories: int


class ClusterDebugScoreBreakdown(BaseModel):
    average_similarity_score: float
    average_title_similarity: float
    average_entity_jaccard: float
    average_keyword_jaccard: float
    average_time_proximity: float
    score_formula: str


class ClusterDebugExplanation(BaseModel):
    grouping_reason: str
    thresholds: ClusterDebugThresholds
    threshold_results: dict[str, bool]
    top_shared_entities: list[str]
    top_shared_keywords: list[str]
    score_breakdown: ClusterDebugScoreBreakdown
    decision_counts: dict[str, int]


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
