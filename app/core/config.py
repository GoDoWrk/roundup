from functools import lru_cache

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
