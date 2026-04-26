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

    with pytest.raises(RuntimeError, match="Set MINIFLUX_API_KEY or MINIFLUX_API_KEY_FILE"):
        run_startup_checks("worker", settings=settings)


def test_worker_startup_check_allows_disabled_scheduler_without_miniflux() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="",
        sample_miniflux_data_path=None,
        scheduler_enabled=False,
    )

    run_startup_checks("worker", settings=settings)


def test_worker_startup_check_accepts_sample_path(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.json"
    sample_path.write_text("[]", encoding="utf-8")

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="",
        demo_mode=True,
        sample_miniflux_data_path=str(sample_path),
    )

    run_startup_checks("worker", settings=settings)


def test_worker_startup_check_fails_demo_mode_without_sample_path() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        demo_mode=True,
        sample_miniflux_data_path=None,
    )

    with pytest.raises(RuntimeError, match="DEMO_MODE=true requires SAMPLE_MINIFLUX_DATA_PATH"):
        run_startup_checks("worker", settings=settings)


def test_worker_startup_check_accepts_miniflux_api_key_file(tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("from-file-token", encoding="utf-8")

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        MINIFLUX_URL="http://miniflux.local",
        MINIFLUX_API_KEY_FILE=str(token_file),
    )

    run_startup_checks("worker", settings=settings)
    assert settings.miniflux_api_token_resolved == "from-file-token"


def test_api_startup_check_does_not_require_miniflux() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", miniflux_api_token="")
    run_startup_checks("api", settings=settings)


def test_settings_accept_new_miniflux_env_aliases() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        MINIFLUX_URL="http://miniflux.local",
        MINIFLUX_API_KEY="secret",
        sample_miniflux_data_path=None,
    )

    assert settings.miniflux_base_url == "http://miniflux.local"
    assert settings.miniflux_api_token == "secret"
    assert settings.has_miniflux_credentials is True


def test_startup_check_rejects_invalid_runtime_limits() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        miniflux_api_token="",
        api_workers=0,
        ingestion_concurrency=0,
        summarization_concurrency=0,
        clustering_batch_size=0,
        clustering_concurrency=0,
        inspector_worker_processes=0,
        scheduler_interval_seconds=0,
    )

    with pytest.raises(RuntimeError) as exc:
        run_startup_checks("api", settings=settings)

    message = str(exc.value)
    assert "API_WORKERS must be greater than 0" in message
    assert "INGESTION_CONCURRENCY must be greater than 0" in message
    assert "SUMMARIZATION_CONCURRENCY must be greater than 0" in message
    assert "CLUSTERING_BATCH_SIZE must be greater than 0" in message
    assert "CLUSTERING_CONCURRENCY must be greater than 0" in message
    assert "INSPECTOR_WORKER_PROCESSES must be greater than 0" in message
    assert "SCHEDULER_INTERVAL_SECONDS must be greater than 0" in message
