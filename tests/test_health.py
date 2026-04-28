from __future__ import annotations

from unittest.mock import Mock

from app.api.routes import health as health_route
from app.api.routes.health import get_health
from app.core.config import Settings


def test_health_endpoint(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["db"] == "ok"
    assert "miniflux_reachable" in payload
    assert "miniflux_usable" in payload
    assert payload["runtime"]["api_workers"] == 1
    assert payload["runtime"]["inspector_worker_processes"] == 1
    assert payload["runtime"]["scheduler_enabled"] is True
    assert payload["runtime"]["ingestion_concurrency"] == 1
    assert payload["runtime"]["summarization_concurrency"] == 1
    assert payload["runtime"]["clustering_batch_size"] == 100
    assert payload["runtime"]["clustering_concurrency"] == 1
    assert "ingestion_active" in payload["runtime"]
    assert "timestamp" in payload


def test_health_route_reports_db_failure_when_probe_raises() -> None:
    db = Mock()
    db.execute.side_effect = RuntimeError("database unavailable")

    response = get_health(db)

    assert response.db == "error"
    assert response.status == "error"
    assert response.runtime.api_workers == 1


def test_health_route_degrades_when_miniflux_probe_raises(monkeypatch) -> None:
    db = Mock()
    settings = Settings(
        miniflux_base_url="http://miniflux.example",
        miniflux_api_token="token",
        demo_mode=False,
    )

    class BrokenMinifluxClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def check_service_reachable(self) -> bool:
            raise RuntimeError("miniflux probe failed")

        def check_credentials(self) -> bool:
            return True

    monkeypatch.setattr(health_route, "get_settings", lambda: settings)
    monkeypatch.setattr(health_route, "MinifluxClient", BrokenMinifluxClient)

    response = get_health(db)

    assert response.status == "degraded"
    assert response.db == "ok"
    assert response.miniflux_reachable is False
    assert response.miniflux_usable is False
