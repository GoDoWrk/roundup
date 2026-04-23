from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.pipeline import run_pipeline


def main() -> None:
    configure_logging()
    settings = get_settings()
    with SessionLocal() as session:
        result = run_pipeline(session, settings)
    print(
        "fetched={0} ingested={1} deduplicated={2} clusters_created={3} clusters_updated={4}".format(
            result.fetched,
            result.ingested,
            result.deduplicated,
            result.clusters_created,
            result.clusters_updated,
        )
    )


if __name__ == "__main__":
    main()
