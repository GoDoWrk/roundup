from __future__ import annotations

from sqlalchemy import create_engine, inspect

from app.db.base import Base


def test_common_query_path_indexes_exist_in_metadata() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    article_indexes = {index["name"] for index in inspector.get_indexes("articles")}
    cluster_indexes = {index["name"] for index in inspector.get_indexes("clusters")}

    assert "ix_articles_published_id" in article_indexes
    assert "ix_articles_fetched_id" in article_indexes
    assert "ix_clusters_last_updated_id" in cluster_indexes
    assert "ix_clusters_status_last_updated" in cluster_indexes
