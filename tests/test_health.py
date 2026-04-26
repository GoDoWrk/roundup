from __future__ import annotations

from unittest.mock import Mock

from app.api.routes.health import get_health


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
    assert response.status == "degraded"
    assert response.runtime.api_workers == 1
