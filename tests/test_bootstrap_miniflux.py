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
