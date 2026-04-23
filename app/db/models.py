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
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    normalized_title: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    cluster_link: Mapped[ClusterArticle | None] = relationship(back_populates="article", uselist=False)

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_canonical_url", "canonical_url"),
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

    normalized_headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    source_links: Mapped[list[ClusterArticle]] = relationship(back_populates="cluster", cascade="all, delete-orphan")
    timeline_events: Mapped[list[ClusterTimelineEvent]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", order_by="ClusterTimelineEvent.timestamp"
    )

    __table_args__ = (
        Index("ix_clusters_last_updated", "last_updated"),
        Index("ix_clusters_status", "status"),
    )


class ClusterArticle(Base):
    __tablename__ = "cluster_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

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
    clusters_created_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clusters_updated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_ingest_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cluster_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
