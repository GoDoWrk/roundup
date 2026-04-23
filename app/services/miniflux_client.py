from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class MinifluxClientError(RuntimeError):
    pass


class MinifluxConfigError(MinifluxClientError):
    pass


class MinifluxRequestError(MinifluxClientError):
    pass


@dataclass
class MinifluxClient:
    base_url: str
    api_token: str
    timeout_seconds: int = 20

    def fetch_entries(self, limit: int = 100) -> list[dict]:
        if not self.api_token.strip():
            raise MinifluxConfigError(
                "MINIFLUX_API_KEY is missing. Set MINIFLUX_API_KEY or configure SAMPLE_MINIFLUX_DATA_PATH "
                "for offline development."
            )

        if not self.base_url.strip():
            raise MinifluxConfigError("MINIFLUX_URL is missing while MINIFLUX_API_KEY is set.")

        endpoint = f"{self.base_url.rstrip('/')}/v1/entries"
        params = {
            "direction": "desc",
            "order": "published_at",
            "status": "unread",
            "limit": limit,
        }
        headers = {
            "X-Auth-Token": self.api_token,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(endpoint, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise MinifluxRequestError(
                f"Miniflux API returned HTTP {exc.response.status_code} from {endpoint}."
            ) from exc
        except httpx.RequestError as exc:
            raise MinifluxRequestError(f"Miniflux request to {endpoint} failed: {exc}") from exc
        except ValueError as exc:
            raise MinifluxRequestError(f"Miniflux response from {endpoint} was not valid JSON.") from exc

        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise MinifluxRequestError("Miniflux response did not include a valid 'entries' list.")

        logger.info("miniflux_fetch_success count=%s endpoint=%s", len(entries), endpoint)
        if not entries:
            logger.info("miniflux_feed_empty endpoint=%s", endpoint)
        return entries
