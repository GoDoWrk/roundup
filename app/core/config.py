from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "roundup"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg2://roundup:roundup@db:5432/roundup"

    miniflux_base_url: str = "http://miniflux:8080"
    miniflux_api_token: str = ""
    miniflux_fetch_limit: int = 100
    miniflux_timeout_seconds: int = 20
    sample_miniflux_data_path: str | None = None

    scheduler_interval_seconds: int = 600

    cluster_score_threshold: float = 0.55
    cluster_time_window_hours: int = 72
    cluster_tie_break_epsilon: float = 0.02
    cluster_min_title_signal: float = 0.72
    cluster_min_entity_overlap: int = 1
    cluster_min_keyword_overlap: int = 2
    cluster_stale_hours: int = 48
    cluster_emerging_hours: int = 24
    cluster_emerging_source_count: int = 3
    cluster_min_sources_for_api: int = 3
    cluster_min_headline_words: int = 3
    cluster_min_detail_words: int = 8
    timeline_dedupe_window_hours: int = 6
    timeline_dedupe_title_similarity: float = 0.85

    api_default_limit: int = 50
    api_max_limit: int = 200

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @field_validator("sample_miniflux_data_path")
    @classmethod
    def _normalize_sample_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @property
    def has_miniflux_credentials(self) -> bool:
        return bool(self.miniflux_base_url.strip() and self.miniflux_api_token.strip())

    @property
    def sample_data_path(self) -> Path | None:
        if not self.sample_miniflux_data_path:
            return None
        return Path(self.sample_miniflux_data_path)

    def validate_startup(self, mode: Literal["api", "worker"]) -> list[str]:
        errors: list[str] = []

        if not self.database_url.strip():
            errors.append("DATABASE_URL must be set.")

        if self.miniflux_fetch_limit <= 0:
            errors.append("MINIFLUX_FETCH_LIMIT must be greater than 0.")
        if self.miniflux_timeout_seconds <= 0:
            errors.append("MINIFLUX_TIMEOUT_SECONDS must be greater than 0.")

        sample_path = self.sample_data_path
        if sample_path is not None and not sample_path.exists():
            errors.append(
                "SAMPLE_MINIFLUX_DATA_PATH points to a missing file: "
                f"{sample_path}. Provide a valid JSON file or clear the variable."
            )

        if mode == "worker":
            if self.miniflux_api_token.strip() and not self.miniflux_base_url.strip():
                errors.append("MINIFLUX_BASE_URL is required when MINIFLUX_API_TOKEN is set.")

            if not self.has_miniflux_credentials and sample_path is None:
                errors.append(
                    "Worker startup requires either live Miniflux credentials "
                    "(MINIFLUX_BASE_URL + MINIFLUX_API_TOKEN) or SAMPLE_MINIFLUX_DATA_PATH "
                    "for offline development."
                )

        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
