from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MinifluxClient:
    base_url: str
    api_token: str
    timeout_seconds: int = 20

    def fetch_entries(self, limit: int = 100) -> list[dict]:
        if not self.api_token:
            logger.warning("MINIFLUX_API_TOKEN is not set; skipping ingestion")
            return []

        endpoint = f"{self.base_url.rstrip('/')}/v1/entries"
        params = {
            "direction": "desc",
            "order": "published_at",
            "limit": limit,
        }
        headers = {
            "X-Auth-Token": self.api_token,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []
        return entries
