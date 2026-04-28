from __future__ import annotations

import httpx

from app.services.miniflux_client import MinifluxClient


def test_miniflux_client_retries_transient_request_errors(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"entries": []}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("connection reset")
            return FakeResponse()

    monkeypatch.setattr("app.services.miniflux_client.httpx.Client", FakeClient)

    client = MinifluxClient(base_url="http://miniflux.local", api_token="token", request_retries=1)

    assert client.fetch_entries(limit=1) == []
    assert calls == 2


def test_miniflux_client_retries_transient_http_status(monkeypatch) -> None:
    calls = 0

    class FakeSuccessResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"entries": []}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                request = httpx.Request("GET", "http://miniflux.local/v1/entries")
                response = httpx.Response(503, request=request)
                response.raise_for_status()
            return FakeSuccessResponse()

    monkeypatch.setattr("app.services.miniflux_client.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.miniflux_client.time.sleep", lambda seconds: None)

    client = MinifluxClient(base_url="http://miniflux.local", api_token="token", request_retries=1)

    assert client.fetch_entries(limit=1) == []
    assert calls == 2
