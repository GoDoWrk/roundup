from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path


def _load_bootstrap_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_miniflux.py"
    spec = importlib.util.spec_from_file_location("bootstrap_miniflux", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mock_public_dns(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if str(host).rstrip(".").lower() in {"example.com", "news.google.com"}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_load_seed_feeds_skips_obviously_unsafe_urls(tmp_path: Path, monkeypatch) -> None:
    _mock_public_dns(monkeypatch)
    module = _load_bootstrap_module()
    seed_file = tmp_path / "feeds.json"
    seed_file.write_text(
        json.dumps(
            [
                "https://example.com/feed.xml",
                "https://example.com/fragment-feed.xml#section",
                "http://localhost/feed.xml",
                "http://localhost./feed.xml",
                "http://127.0.0.1/internal",
                "http://[::1]/internal",
                "http://169.254.169.254/latest/meta-data",
                "https://user:password@example.com/feed.xml",
                "https://example.com/feed.xml?token=secret",
                "ftp://example.com/feed.xml",
            ]
        ),
        encoding="utf-8",
    )

    feeds = module._load_seed_feeds(seed_file, "Roundup")

    assert [feed.url for feed in feeds] == [
        "https://example.com/feed.xml",
        "https://example.com/fragment-feed.xml",
    ]
    assert feeds[0].category == "Roundup"
    assert feeds[0].priority == "normal"
    assert feeds[0].allow_service_content is False
    assert feeds[0].promote_to_home is True


def test_load_seed_feeds_allows_private_urls_only_when_explicitly_enabled(tmp_path: Path) -> None:
    module = _load_bootstrap_module()
    seed_file = tmp_path / "feeds.json"
    seed_file.write_text(
        json.dumps(
            [
                "http://localhost/feed.xml",
                "http://127.0.0.1/internal",
                "http://[::1]/internal",
                "https://user:password@example.com/feed.xml",
                "https://example.com/feed.xml?token=secret",
            ]
        ),
        encoding="utf-8",
    )

    feeds = module._load_seed_feeds(seed_file, "Roundup", allow_private_network=True)

    assert [feed.url for feed in feeds] == [
        "http://localhost/feed.xml",
        "http://127.0.0.1/internal",
        "http://[::1]/internal",
    ]


def test_load_seed_feeds_accepts_optional_quality_controls(tmp_path: Path, monkeypatch) -> None:
    _mock_public_dns(monkeypatch)
    module = _load_bootstrap_module()
    seed_file = tmp_path / "feeds.json"
    seed_file.write_text(
        json.dumps(
            [
                {
                    "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS",
                    "category": "Google News",
                    "priority": "low",
                    "allow_service_content": False,
                    "promote_to_home": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    feeds = module._load_seed_feeds(seed_file, "Roundup")

    assert len(feeds) == 1
    assert feeds[0].priority == "low"
    assert feeds[0].allow_service_content is False
    assert feeds[0].promote_to_home is False


def test_seed_feeds_counts_request_errors_without_aborting() -> None:
    module = _load_bootstrap_module()

    class FakeClient:
        def post(self, *args, **kwargs):
            raise module.httpx.ReadTimeout("timed out")

    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap.client = FakeClient()
    bootstrap._get_categories = lambda token: {"News": 1}
    bootstrap._existing_feed_urls = lambda token: set()
    bootstrap._ensure_category = lambda token, title, existing: 1

    imported, skipped, failed = bootstrap.seed_feeds(
        "token",
        [module.SeedFeed(url="https://example.com/feed.xml", category="News")],
    )

    assert (imported, skipped, failed) == (0, 0, 1)


def test_seed_feeds_retries_transient_create_feed_errors() -> None:
    module = _load_bootstrap_module()
    calls = 0

    class FakeResponse:
        status_code = 201
        text = ""

    class FakeClient:
        def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise module.httpx.ReadTimeout("timed out")
            return FakeResponse()

    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap.client = FakeClient()
    bootstrap.request_retries = 1
    bootstrap._get_categories = lambda token: {"News": 1}
    bootstrap._existing_feed_urls = lambda token: set()
    bootstrap._ensure_category = lambda token, title, existing: 1

    imported, skipped, failed = bootstrap.seed_feeds(
        "token",
        [module.SeedFeed(url="https://example.com/feed.xml", category="News")],
    )

    assert (imported, skipped, failed) == (1, 0, 0)
    assert calls == 2


def test_seed_feeds_counts_category_errors_without_aborting() -> None:
    module = _load_bootstrap_module()

    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap._get_categories = lambda token: {}
    bootstrap._existing_feed_urls = lambda token: set()

    def _raise_category_error(token, title, existing):
        raise RuntimeError("category create failed")

    bootstrap._ensure_category = _raise_category_error

    imported, skipped, failed = bootstrap.seed_feeds(
        "token",
        [
            module.SeedFeed(url="https://example.com/feed-one.xml", category="News"),
            module.SeedFeed(url="https://example.com/feed-two.xml", category="News"),
        ],
    )

    assert (imported, skipped, failed) == (0, 0, 2)


def test_verify_api_token_request_error_returns_false() -> None:
    module = _load_bootstrap_module()

    class FakeClient:
        def get(self, *args, **kwargs):
            raise module.httpx.ReadTimeout("timed out")

    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap.client = FakeClient()

    assert bootstrap.verify_api_token("token") is False


def test_trigger_refresh_request_error_warns_without_aborting() -> None:
    module = _load_bootstrap_module()

    class FakeClient:
        def put(self, *args, **kwargs):
            raise module.httpx.ConnectError("connection reset")

    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap.client = FakeClient()

    bootstrap.trigger_refresh("token")


def test_wait_for_entries_after_refresh_returns_when_entries_appear(monkeypatch) -> None:
    module = _load_bootstrap_module()
    calls = 0

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, entries):
            self._entries = entries

        def json(self):
            return {"entries": self._entries}

    class FakeClient:
        def get(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse([] if calls == 1 else [{"id": 1}])

    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    bootstrap = object.__new__(module.MinifluxBootstrap)
    bootstrap.base_url = "http://miniflux:8080"
    bootstrap.client = FakeClient()
    bootstrap.request_retries = 0

    assert bootstrap.wait_for_entries_after_refresh("token", max_wait_seconds=10, retry_interval_seconds=1) is True
    assert calls == 2
