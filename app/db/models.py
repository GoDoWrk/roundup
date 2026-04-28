from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_topic: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    subtopic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    geography: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    cluster_link: Mapped[ClusterArticle | None] = relationship(back_populates="article", uselist=False)

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_published_id", "published_at", "id"),
        Index("ix_articles_fetched_id", "fetched_at", "id"),
        Index("ix_articles_canonical_url", "canonical_url"),
        Index("ix_articles_publisher", "publisher"),
        Index("ix_articles_topic", "topic"),
        Index("ix_articles_primary_subtopic", "primary_topic", "subtopic"),
    )


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    what_changed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="emerging")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    promotion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    normalized_headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    key_facts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    related_cluster_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_topic: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    subtopic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    geography: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    source_links: Mapped[list[ClusterArticle]] = relationship(back_populates="cluster", cascade="all, delete-orphan")
    timeline_events: Mapped[list[ClusterTimelineEvent]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", order_by="ClusterTimelineEvent.timestamp"
    )

    __table_args__ = (
        Index("ix_clusters_last_updated", "last_updated"),
        Index("ix_clusters_last_updated_id", "last_updated", "id"),
        Index("ix_clusters_status", "status"),
        Index("ix_clusters_status_last_updated", "status", "last_updated", "id"),
        Index("ix_clusters_score_last_updated", "score", "last_updated", "id"),
        Index("ix_clusters_topic", "topic"),
        Index("ix_clusters_primary_subtopic", "primary_topic", "subtopic"),
    )


class ClusterArticle(Base):
    __tablename__ = "cluster_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    heuristic_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    cluster: Mapped[Cluster] = relationship(back_populates="source_links")
    article: Mapped[Article] = relationship(back_populates="cluster_link")

    __table_args__ = (UniqueConstraint("cluster_id", "article_id", name="uq_cluster_article"),)


class ClusterTimelineEvent(Base):
    __tablename__ = "cluster_timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(Text, nullable=False)

    cluster: Mapped[Cluster] = relationship(back_populates="timeline_events")

    __table_args__ = (Index("ix_cluster_timeline_cluster_timestamp", "cluster_id", "timestamp"),)


class PipelineStats(Base):
    __tablename__ = "pipeline_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    articles_ingested_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_deduplicated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_malformed_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingest_source_failures_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_articles_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_articles_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_duplicate_articles_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_articles_malformed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_failed_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    configured_feed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_feed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feeds_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feeds_with_new_articles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    miniflux_entries_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_fetched_raw: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_rejected_quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_rejected_stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_rejected_service_finance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_created_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_updated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_candidates_evaluated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_signal_rejected_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_attach_decisions_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_new_decisions_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_low_confidence_new_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_validation_rejected_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_timeline_events_deduplicated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_promoted_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_hidden_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_active_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_promotion_attempts_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cluster_promotion_failures_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_candidate_clusters_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_clusters_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_clusters_hidden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_clusters_promoted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_visible_clusters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_ingest_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cluster_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
