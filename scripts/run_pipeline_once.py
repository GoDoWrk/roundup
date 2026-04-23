from __future__ import annotations

from uuid import uuid4

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.session import SessionLocal
from app.services.pipeline import run_pipeline


def main() -> None:
    configure_logging()
    settings = get_settings()
    run_startup_checks("worker", settings=settings)
    run_id = uuid4().hex[:8]
    with SessionLocal() as session:
        result = run_pipeline(session, settings, run_id=run_id)
    print(
        "run_id={0} source={1} fetched={2} ingested={3} deduplicated={4} malformed={5} clusters_created={6} clusters_updated={7}".format(
            run_id,
            result.ingestion_source,
            result.fetched,
            result.ingested,
            result.deduplicated,
            result.malformed,
            result.clusters_created,
            result.clusters_updated,
        )
    )


if __name__ == "__main__":
    main()
