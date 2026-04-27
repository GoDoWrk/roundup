from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "roundup"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg2://roundup:roundup@db:5432/roundup"

    miniflux_base_url: str = Field(
        default="http://miniflux:8080",
        validation_alias=AliasChoices("MINIFLUX_URL", "MINIFLUX_BASE_URL", "miniflux_base_url"),
    )
    miniflux_api_token: str = Field(
        default="",
        validation_alias=AliasChoices("MINIFLUX_API_KEY", "MINIFLUX_API_TOKEN", "miniflux_api_token"),
    )
    miniflux_api_token_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "MINIFLUX_API_KEY_FILE",
            "MINIFLUX_API_TOKEN_FILE",
            "miniflux_api_token_file",
        ),
    )
    ingest_max_total_articles: int = Field(
        default=1000,
        validation_alias=AliasChoices(
            "ROUNDUP_INGEST_MAX_TOTAL_ARTICLES",
            "MINIFLUX_FETCH_LIMIT",
            "miniflux_fetch_limit",
            "ingest_max_total_articles",
        ),
    )
    ingest_max_articles_per_feed: int = Field(
        default=10,
        validation_alias=AliasChoices("ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED", "ingest_max_articles_per_feed"),
    )
    ingest_lookback_hours: int = Field(
        default=24,
        validation_alias=AliasChoices("ROUNDUP_INGEST_LOOKBACK_HOURS", "ingest_lookback_hours"),
    )
    ingest_max_pages: int = Field(
        default=10,
        validation_alias=AliasChoices("ROUNDUP_INGEST_MAX_PAGES", "ingest_max_pages"),
    )
    ingest_category_quotas_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ROUNDUP_INGEST_CATEGORY_QUOTAS_ENABLED", "ingest_category_quotas_enabled"),
    )
    miniflux_timeout_seconds: int = 20
    allow_private_feed_urls: bool = Field(
        default=False,
        validation_alias=AliasChoices("ROUNDUP_ALLOW_PRIVATE_FEED_URLS", "allow_private_feed_urls"),
    )
    demo_mode: bool = False
    sample_miniflux_data_path: str | None = None

    api_workers: int = 1
    ingestion_concurrency: int = 1
    summarization_concurrency: int = 1
    clustering_batch_size: int = 100
    clustering_concurrency: int = 1
    inspector_worker_processes: int = 1
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 600

    cluster_score_threshold: float = 0.55
    cluster_time_window_hours: int = 72
    cluster_tie_break_epsilon: float = 0.02
    cluster_min_title_signal: float = 0.72
    cluster_min_entity_overlap: int = 1
    cluster_min_keyword_overlap: int = 2
    cluster_min_topic_semantic_score: float = 0.38
    cluster_attach_override_min_title_similarity: float = 0.30
    cluster_attach_override_min_time_proximity: float = 0.80
    cluster_stale_hours: int = 48
    cluster_emerging_hours: int = 24
    cluster_emerging_source_count: int = 3
    cluster_min_sources_for_api: int = 3
    cluster_min_distinct_sources_for_api: int = 2
    cluster_min_sources_for_top_stories: int = 2
    cluster_min_sources_for_developing_stories: int = 2
    cluster_show_just_in_single_source: bool = True
    cluster_homepage_top_limit: int = 6
    cluster_homepage_developing_limit: int = 8
    cluster_homepage_just_in_limit: int = 10
    cluster_min_headline_words: int = 3
    cluster_min_detail_words: int = 8
    timeline_dedupe_window_hours: int = 6
    timeline_dedupe_title_similarity: float = 0.85

    api_default_limit: int = 50
    api_max_limit: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    @field_validator("sample_miniflux_data_path")
    @classmethod
    def _normalize_sample_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @property
    def miniflux_api_token_resolved(self) -> str:
        direct = self.miniflux_api_token.strip()
        if direct:
            return direct

        secret_file = (self.miniflux_api_token_file or "").strip()
        if not secret_file:
            return ""

        path = Path(secret_file)
        if not path.exists() or not path.is_file():
            return ""

        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @property
    def has_miniflux_credentials(self) -> bool:
        return bool(self.miniflux_base_url.strip() and self.miniflux_api_token_resolved)

    @property
    def sample_data_path(self) -> Path | None:
        if not self.sample_miniflux_data_path:
            return None
        return Path(self.sample_miniflux_data_path)

    @property
    def miniflux_fetch_limit(self) -> int:
        return self.ingest_max_total_articles

    def validate_startup(self, mode: Literal["api", "worker"]) -> list[str]:
        errors: list[str] = []

        if not self.database_url.strip():
            errors.append("DATABASE_URL must be set.")

        if self.ingest_max_total_articles <= 0:
            errors.append("ROUNDUP_INGEST_MAX_TOTAL_ARTICLES must be greater than 0.")
        if self.ingest_max_articles_per_feed <= 0:
            errors.append("ROUNDUP_INGEST_MAX_ARTICLES_PER_FEED must be greater than 0.")
        if self.ingest_lookback_hours <= 0:
            errors.append("ROUNDUP_INGEST_LOOKBACK_HOURS must be greater than 0.")
        if self.ingest_max_pages <= 0:
            errors.append("ROUNDUP_INGEST_MAX_PAGES must be greater than 0.")
        if self.miniflux_timeout_seconds <= 0:
            errors.append("MINIFLUX_TIMEOUT_SECONDS must be greater than 0.")
        if self.api_workers <= 0:
            errors.append("API_WORKERS must be greater than 0.")
        if self.ingestion_concurrency <= 0:
            errors.append("INGESTION_CONCURRENCY must be greater than 0.")
        if self.summarization_concurrency <= 0:
            errors.append("SUMMARIZATION_CONCURRENCY must be greater than 0.")
        if self.clustering_batch_size <= 0:
            errors.append("CLUSTERING_BATCH_SIZE must be greater than 0.")
        if self.clustering_concurrency <= 0:
            errors.append("CLUSTERING_CONCURRENCY must be greater than 0.")
        if self.cluster_min_distinct_sources_for_api <= 0:
            errors.append("CLUSTER_MIN_DISTINCT_SOURCES_FOR_API must be greater than 0.")
        if self.inspector_worker_processes <= 0:
            errors.append("INSPECTOR_WORKER_PROCESSES must be greater than 0.")
        if self.scheduler_interval_seconds <= 0:
            errors.append("SCHEDULER_INTERVAL_SECONDS must be greater than 0.")

        sample_path = self.sample_data_path
        if sample_path is not None and not sample_path.exists():
            errors.append(
                "SAMPLE_MINIFLUX_DATA_PATH points to a missing file: "
                f"{sample_path}. Provide a valid JSON file or clear the variable."
            )

        if mode == "worker":
            if not self.scheduler_enabled:
                return errors

            if self.demo_mode:
                if sample_path is None:
                    errors.append(
                        "DEMO_MODE=true requires SAMPLE_MINIFLUX_DATA_PATH to be set to a valid JSON file."
                    )
                return errors

            if not self.miniflux_base_url.strip():
                errors.append("MINIFLUX_URL must be set when DEMO_MODE is false.")

            if not self.miniflux_api_token_resolved:
                errors.append(
                    "Set MINIFLUX_API_KEY or MINIFLUX_API_KEY_FILE before starting worker mode "
                    "(DEMO_MODE=false requires live Miniflux credentials)."
                )

        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
