from __future__ import annotations

from app.core.config import Settings
from app.core.logging import redact_secrets


def test_settings_default_blocks_private_feed_urls() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    assert settings.allow_private_feed_urls is False


def test_settings_accepts_private_feed_url_override() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        ROUNDUP_ALLOW_PRIVATE_FEED_URLS=True,
    )

    assert settings.allow_private_feed_urls is True


def test_log_redaction_masks_secret_assignments_and_mapping_values() -> None:
    message = redact_secrets("password=super-secret token=abc123 api_key=key-456 https://user:pass@example.com/feed")
    mapping = redact_secrets({"X-Auth-Token": "abc123", "safe": "visible"})

    assert message == "password=<redacted> token=<redacted> api_key=<redacted> https://<redacted>@example.com/feed"
    assert mapping == {"X-Auth-Token": "<redacted>", "safe": "visible"}
