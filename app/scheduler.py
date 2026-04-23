from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.pipeline import run_pipeline

configure_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    interval = max(settings.scheduler_interval_seconds, 30)

    logger.info("scheduler_started interval_seconds=%s", interval)
    while True:
        started = time.monotonic()
        with SessionLocal() as session:
            try:
                run_pipeline(session, settings)
            except Exception:
                session.rollback()
                logger.exception("pipeline_run_failed")

        elapsed = time.monotonic() - started
        sleep_seconds = max(1, interval - int(elapsed))
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
