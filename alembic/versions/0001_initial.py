"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-22 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("dedupe_hash", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("dedupe_hash", name="uq_articles_dedupe_hash"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"], unique=False)
    op.create_index("ix_articles_canonical_url", "articles", ["canonical_url"], unique=False)

    op.create_table(
        "clusters",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("what_changed", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("normalized_headline", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_clusters_last_updated", "clusters", ["last_updated"], unique=False)
    op.create_index("ix_clusters_status", "clusters", ["status"], unique=False)

    op.create_table(
        "cluster_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.String(length=64), sa.ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.UniqueConstraint("cluster_id", "article_id", name="uq_cluster_article"),
        sa.UniqueConstraint("article_id", name="uq_cluster_articles_article_id"),
    )

    op.create_table(
        "cluster_timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.String(length=64), sa.ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_cluster_timeline_cluster_timestamp",
        "cluster_timeline_events",
        ["cluster_id", "timestamp"],
        unique=False,
    )

    op.create_table(
        "pipeline_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("articles_ingested_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("articles_deduplicated_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clusters_created_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clusters_updated_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_ingest_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cluster_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pipeline_stats")
    op.drop_index("ix_cluster_timeline_cluster_timestamp", table_name="cluster_timeline_events")
    op.drop_table("cluster_timeline_events")
    op.drop_table("cluster_articles")
    op.drop_index("ix_clusters_status", table_name="clusters")
    op.drop_index("ix_clusters_last_updated", table_name="clusters")
    op.drop_table("clusters")
    op.drop_index("ix_articles_canonical_url", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_table("articles")
