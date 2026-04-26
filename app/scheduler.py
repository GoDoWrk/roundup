from __future__ import annotations

import logging
import time
from uuid import uuid4

from sqlalchemy import text
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.session import SessionLocal
from app.services.pipeline import run_pipeline

configure_logging()
logger = logging.getLogger(__name__)

SCHEDULER_LOCK_KEY = 917263401


def _try_acquire_scheduler_lock(session) -> bool:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return True
    return bool(session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_LOCK_KEY}).scalar())


def _release_scheduler_lock(session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEDULER_LOCK_KEY})


def main() -> None:
    settings = get_settings()
    run_startup_checks("worker", settings=settings)
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled exiting")
        return

    interval = max(settings.scheduler_interval_seconds, 30)

    logger.info(
        "scheduler_started interval_seconds=%s ingestion_concurrency=%s summarization_concurrency=%s clustering_batch_size=%s clustering_concurrency=%s",
        interval,
        settings.ingestion_concurrency,
        settings.summarization_concurrency,
        settings.clustering_batch_size,
        settings.clustering_concurrency,
    )
    while True:
        run_id = uuid4().hex[:8]
        started = time.monotonic()
        with SessionLocal() as session:
            try:
                if not _try_acquire_scheduler_lock(session):
                    logger.info("pipeline_cycle_skipped run_id=%s reason=scheduler_lock_held", run_id)
                    session.rollback()
                    time.sleep(interval)
                    continue
                run_pipeline(session, settings, run_id=run_id)
            except Exception:
                session.rollback()
                logger.exception("pipeline_run_failed run_id=%s", run_id)
            finally:
                try:
                    _release_scheduler_lock(session)
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception("scheduler_lock_release_failed run_id=%s", run_id)

        elapsed = time.monotonic() - started
        logger.info("pipeline_cycle_finished run_id=%s duration_seconds=%.2f", run_id, elapsed)
        sleep_seconds = max(1, interval - int(elapsed))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
