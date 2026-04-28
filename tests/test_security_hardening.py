from __future__ import annotations

import socket

from app.core.config import Settings
from app.core.logging import redact_secrets
from app.core.url_security import safe_feed_url


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
    message = redact_secrets(
        "password=super-secret token=abc123 api_key=key-456 "
        "Authorization: Bearer live-token-12345 postgresql://user:pass@db:5432/roundup"
    )
    mapping = redact_secrets({"X-Auth-Token": "abc123", "safe": "visible"})

    assert message == (
        "password=<redacted> token=<redacted> api_key=<redacted> "
        "Authorization: <redacted> postgresql://<redacted>@db:5432/roundup"
    )
    assert mapping == {"X-Auth-Token": "<redacted>", "safe": "visible"}


def _mock_public_dns(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if str(host).rstrip(".").lower() in {"example.com", "news.example"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_feed_url_validator_blocks_obvious_ssrf_targets_and_secret_query_values(monkeypatch) -> None:
    _mock_public_dns(monkeypatch)

    assert safe_feed_url("https://example.com/feed.xml#fragment") == "https://example.com/feed.xml"
    assert safe_feed_url("http://localhost/feed.xml") is None
    assert safe_feed_url("http://localhost./feed.xml") is None
    assert safe_feed_url("http://127.0.0.1/internal") is None
    assert safe_feed_url("http://[::1]/internal") is None
    assert safe_feed_url("http://169.254.169.254/latest/meta-data") is None
    assert safe_feed_url("https://user:password@example.com/feed.xml") is None
    assert safe_feed_url("https://example.com/feed.xml?key=secret") is None


def test_feed_url_validator_allows_private_network_only_with_explicit_override() -> None:
    assert safe_feed_url("http://127.0.0.1/internal", allow_private_network=True) == "http://127.0.0.1/internal"
    assert safe_feed_url("http://localhost/feed.xml", allow_private_network=True) == "http://localhost/feed.xml"
    assert safe_feed_url("https://user:password@example.com/feed.xml", allow_private_network=True) is None
    assert safe_feed_url("https://example.com/feed.xml?token=secret", allow_private_network=True) is None


def test_feed_url_validator_blocks_hostnames_that_resolve_private_networks(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if str(host).rstrip(".").lower() == "news.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 0))]
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert safe_feed_url("https://news.example/feed.xml") is None
