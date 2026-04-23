from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.startup_checks import run_startup_checks
from app.db.session import SessionLocal
from app.services.pipeline import run_pipeline

configure_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    run_startup_checks("worker", settings=settings)
    interval = max(settings.scheduler_interval_seconds, 30)

    logger.info("scheduler_started interval_seconds=%s", interval)
    while True:
        run_id = uuid4().hex[:8]
        started = time.monotonic()
        with SessionLocal() as session:
            try:
                run_pipeline(session, settings, run_id=run_id)
            except Exception:
                session.rollback()
                logger.exception("pipeline_run_failed run_id=%s", run_id)

        elapsed = time.monotonic() - started
        logger.info("pipeline_cycle_finished run_id=%s duration_seconds=%.2f", run_id, elapsed)
        sleep_seconds = max(1, interval - int(elapsed))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
