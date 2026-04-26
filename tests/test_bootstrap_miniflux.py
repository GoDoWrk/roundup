from __future__ import annotations

import importlib.util
import json
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


def test_load_seed_feeds_skips_obviously_unsafe_urls(tmp_path: Path) -> None:
    module = _load_bootstrap_module()
    seed_file = tmp_path / "feeds.json"
    seed_file.write_text(
        json.dumps(
            [
                "https://example.com/feed.xml",
                "http://localhost/feed.xml",
                "http://127.0.0.1/internal",
                "ftp://example.com/feed.xml",
            ]
        ),
        encoding="utf-8",
    )

    feeds = module._load_seed_feeds(seed_file, "Roundup")

    assert [feed.url for feed in feeds] == ["https://example.com/feed.xml"]
    assert feeds[0].category == "Roundup"


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
