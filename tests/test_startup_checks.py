from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.startup_checks import run_startup_checks


def test_worker_startup_check_fails_without_miniflux_or_sample() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="",
        sample_miniflux_data_path=None,
    )

    with pytest.raises(RuntimeError, match="Worker startup requires either live Miniflux credentials"):
        run_startup_checks("worker", settings=settings)


def test_worker_startup_check_accepts_sample_path(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.json"
    sample_path.write_text("[]", encoding="utf-8")

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="",
        sample_miniflux_data_path=str(sample_path),
    )

    run_startup_checks("worker", settings=settings)


def test_api_startup_check_does_not_require_miniflux() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", miniflux_api_token="")
    run_startup_checks("api", settings=settings)
