from __future__ import annotations

from sqlalchemy import func, or_, select

from app.core.logging import configure_logging
from app.db.models import Article, Cluster, ClusterArticle
from app.db.session import SessionLocal


def main() -> None:
    configure_logging()

    with SessionLocal() as session:
        demo_article_ids = session.scalars(
            select(Article.id).where(
                or_(
                    Article.canonical_url.like("https://demo.roundup.local/%"),
                    Article.publisher.like("Demo Wire%"),
                    Article.dedupe_hash.like("promo-zeta42-%"),
                )
            )
        ).all()

        deleted_articles = 0
        if demo_article_ids:
            deleted_articles = (
                session.query(Article)
                .filter(Article.id.in_(demo_article_ids))
                .delete(synchronize_session=False)
            )
            session.flush()

        orphan_cluster_ids = session.scalars(
            select(Cluster.id)
            .outerjoin(ClusterArticle, ClusterArticle.cluster_id == Cluster.id)
            .group_by(Cluster.id)
            .having(func.count(ClusterArticle.id) == 0)
        ).all()

        deleted_clusters = 0
        if orphan_cluster_ids:
            deleted_clusters = (
                session.query(Cluster)
                .filter(Cluster.id.in_(orphan_cluster_ids))
                .delete(synchronize_session=False)
            )

        session.commit()

        print(
            "purge_demo_data deleted_articles={0} deleted_orphan_clusters={1}".format(
                deleted_articles,
                deleted_clusters,
            )
        )


if __name__ == "__main__":
    main()
