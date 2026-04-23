from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("bootstrap_miniflux")


@dataclass(frozen=True)
class SeedFeed:
    url: str
    category: str


def _load_seed_feeds(path: Path, default_category: str) -> list[SeedFeed]:
    if not path.exists():
        raise RuntimeError(f"Feed seed file does not exist: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError(f"Feed seed file must be a JSON array: {path}")

    parsed: list[SeedFeed] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        if isinstance(item, str):
            feed_url = item.strip()
            category = default_category
        elif isinstance(item, dict):
            feed_url = str(item.get("url", "")).strip()
            category = str(item.get("category", "")).strip() or default_category
        else:
            raise RuntimeError(f"Feed seed entry #{idx} must be a string or object.")

        if not feed_url:
            logger.warning("miniflux_seed_feed_skipped reason=missing_url index=%s", idx)
            continue

        key = feed_url.lower()
        if key in seen:
            logger.info("miniflux_seed_feed_skipped reason=duplicate_in_seed url=%s", feed_url)
            continue

        seen.add(key)
        parsed.append(SeedFeed(url=feed_url, category=category))

    return parsed


class MinifluxBootstrap:
    def __init__(
        self,
        *,
        base_url: str,
        admin_username: str,
        admin_password: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_auth = (admin_username, admin_password)
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def wait_until_ready(self, *, max_wait_seconds: int, retry_interval_seconds: int) -> None:
        deadline = time.monotonic() + max_wait_seconds
        attempt = 0
        endpoint = f"{self.base_url}/healthcheck"
        while time.monotonic() < deadline:
            attempt += 1
            try:
                response = self.client.get(endpoint)
                if response.status_code == 200:
                    logger.info("miniflux_bootstrap_reachable endpoint=%s attempts=%s", endpoint, attempt)
                    return
                logger.warning(
                    "miniflux_bootstrap_waiting attempt=%s status_code=%s endpoint=%s",
                    attempt,
                    response.status_code,
                    endpoint,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "miniflux_bootstrap_waiting attempt=%s reason=request_error error=%s endpoint=%s",
                    attempt,
                    exc,
                    endpoint,
                )
            time.sleep(max(retry_interval_seconds, 1))

        raise RuntimeError(f"Miniflux was not reachable at {endpoint} within {max_wait_seconds} seconds.")

    def verify_admin(self) -> int:
        endpoint = f"{self.base_url}/v1/me"
        response = self.client.get(endpoint, auth=self.admin_auth)
        if response.status_code != 200:
            raise RuntimeError(
                "Failed to authenticate Miniflux admin credentials. "
                f"status={response.status_code} endpoint={endpoint} body={response.text[:300]}"
            )
        payload = response.json()
        user_id = int(payload.get("id") or 0)
        if user_id <= 0:
            raise RuntimeError("Miniflux /v1/me did not return a valid user id for admin account.")
        logger.info("miniflux_admin_verified username=%s user_id=%s", self.admin_auth[0], user_id)
        return user_id

    def verify_api_token(self, token: str) -> bool:
        endpoint = f"{self.base_url}/v1/me"
        response = self.client.get(endpoint, headers={"X-Auth-Token": token})
        return response.status_code == 200

    def create_api_key(self, description: str) -> str:
        endpoint = f"{self.base_url}/v1/api-keys"
        response = self.client.post(endpoint, auth=self.admin_auth, json={"description": description})
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                "Unable to create Miniflux API key. "
                f"status={response.status_code} endpoint={endpoint} body={response.text[:300]}"
            )
        payload = response.json()
        token = str(payload.get("token", "")).strip()
        if not token:
            raise RuntimeError("Miniflux API key creation succeeded but response did not include token.")
        logger.info("miniflux_api_key_created description=%s key_id=%s", description, payload.get("id"))
        return token

    def _get_categories(self, token: str) -> dict[str, int]:
        endpoint = f"{self.base_url}/v1/categories"
        response = self.client.get(endpoint, headers={"X-Auth-Token": token})
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to read Miniflux categories status={response.status_code} endpoint={endpoint}"
            )
        payload = response.json()
        categories: dict[str, int] = {}
        for item in payload:
            title = str(item.get("title") or "").strip()
            category_id = int(item.get("id") or 0)
            if title and category_id > 0:
                categories[title] = category_id
        return categories

    def _ensure_category(self, token: str, title: str, existing: dict[str, int]) -> int:
        if title in existing:
            return existing[title]

        endpoint = f"{self.base_url}/v1/categories"
        response = self.client.post(endpoint, headers={"X-Auth-Token": token}, json={"title": title})
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                "Failed creating Miniflux category. "
                f"status={response.status_code} title={title} endpoint={endpoint} body={response.text[:300]}"
            )
        payload = response.json()
        category_id = int(payload.get("id") or 0)
        if category_id <= 0:
            raise RuntimeError(f"Miniflux returned invalid category id for category '{title}'.")
        existing[title] = category_id
        logger.info("miniflux_feed_category_created title=%s category_id=%s", title, category_id)
        return category_id

    def _existing_feed_urls(self, token: str) -> set[str]:
        endpoint = f"{self.base_url}/v1/feeds"
        response = self.client.get(endpoint, headers={"X-Auth-Token": token})
        if response.status_code != 200:
            raise RuntimeError(f"Failed to read Miniflux feeds status={response.status_code} endpoint={endpoint}")
        payload = response.json()
        urls: set[str] = set()
        for item in payload:
            feed_url = str(item.get("feed_url") or "").strip().lower()
            if feed_url:
                urls.add(feed_url)
        return urls

    def seed_feeds(self, token: str, feeds: list[SeedFeed]) -> tuple[int, int, int]:
        existing_categories = self._get_categories(token)
        existing_feed_urls = self._existing_feed_urls(token)

        imported = 0
        skipped = 0
        failed = 0
        for feed in feeds:
            normalized_url = feed.url.lower()
            if normalized_url in existing_feed_urls:
                skipped += 1
                logger.info("miniflux_feed_seed_skipped reason=already_exists url=%s", feed.url)
                continue

            category_id = self._ensure_category(token, feed.category, existing_categories)
            endpoint = f"{self.base_url}/v1/feeds"
            response = self.client.post(
                endpoint,
                headers={"X-Auth-Token": token},
                json={"feed_url": feed.url, "category_id": category_id},
            )

            if response.status_code in {200, 201}:
                imported += 1
                existing_feed_urls.add(normalized_url)
                logger.info("miniflux_feed_seed_imported url=%s category=%s", feed.url, feed.category)
                continue

            body_lower = response.text.lower()
            if "duplicated feed" in body_lower:
                skipped += 1
                existing_feed_urls.add(normalized_url)
                logger.info("miniflux_feed_seed_skipped reason=duplicated_feed url=%s", feed.url)
                continue

            failed += 1
            logger.warning(
                "miniflux_feed_seed_failed url=%s category=%s status=%s body=%s",
                feed.url,
                feed.category,
                response.status_code,
                response.text[:300],
            )

        return imported, skipped, failed

    def trigger_refresh(self, token: str) -> None:
        endpoint = f"{self.base_url}/v1/feeds/refresh"
        response = self.client.put(endpoint, headers={"X-Auth-Token": token})
        if response.status_code not in {200, 202, 204}:
            logger.warning(
                "miniflux_refresh_all_feeds_failed status=%s endpoint=%s body=%s",
                response.status_code,
                endpoint,
                response.text[:300],
            )
            return
        logger.info("miniflux_refresh_all_feeds_requested")


def _write_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token.strip(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows containers and some filesystems do not support chmod.
        pass


def _read_token_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _required_env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if value:
        return value
    raise RuntimeError(f"Required environment variable is missing or empty: {name}")


def main() -> None:
    base_url = _required_env("MINIFLUX_URL", "http://miniflux:8080")
    admin_username = _required_env("MINIFLUX_ADMIN_USERNAME", "roundup_admin")
    admin_password = _required_env("MINIFLUX_ADMIN_PASSWORD", "roundup_admin_change_me")
    token_file = Path(_required_env("MINIFLUX_API_KEY_FILE", "/miniflux-bootstrap/miniflux_api_key"))
    feed_seed_file = Path(_required_env("MINIFLUX_BOOTSTRAP_FEEDS_FILE", "/app/data/miniflux_seed_feeds.json"))
    api_key_description = _required_env("MINIFLUX_API_KEY_DESCRIPTION", "Roundup ingestion API key")
    default_category = _required_env("MINIFLUX_BOOTSTRAP_DEFAULT_CATEGORY", "Roundup Starter Feeds")
    timeout_seconds = int(os.getenv("MINIFLUX_BOOTSTRAP_TIMEOUT_SECONDS", "10"))
    max_wait_seconds = int(os.getenv("MINIFLUX_BOOTSTRAP_WAIT_SECONDS", "240"))
    retry_interval_seconds = int(os.getenv("MINIFLUX_BOOTSTRAP_RETRY_INTERVAL_SECONDS", "3"))

    logger.info(
        "miniflux_bootstrap_started base_url=%s feed_seed_file=%s token_file=%s",
        base_url,
        feed_seed_file,
        token_file,
    )

    feeds = _load_seed_feeds(feed_seed_file, default_category=default_category)
    if not feeds:
        raise RuntimeError(f"No usable seed feeds found in {feed_seed_file}.")

    bootstrap = MinifluxBootstrap(
        base_url=base_url,
        admin_username=admin_username,
        admin_password=admin_password,
        timeout_seconds=timeout_seconds,
    )
    try:
        bootstrap.wait_until_ready(
            max_wait_seconds=max_wait_seconds,
            retry_interval_seconds=retry_interval_seconds,
        )
        bootstrap.verify_admin()

        token = _read_token_file(token_file)
        if token and bootstrap.verify_api_token(token):
            logger.info("miniflux_api_key_reused token_file=%s", token_file)
        else:
            if token:
                logger.warning("miniflux_api_key_invalid_regenerating token_file=%s", token_file)
            token = bootstrap.create_api_key(description=api_key_description)
            _write_token_file(token_file, token)
            logger.info("miniflux_api_key_written token_file=%s", token_file)

        imported, skipped, failed = bootstrap.seed_feeds(token, feeds)
        logger.info(
            "miniflux_feed_seed_complete total=%s imported=%s skipped=%s failed=%s",
            len(feeds),
            imported,
            skipped,
            failed,
        )
        bootstrap.trigger_refresh(token)

        if failed == len(feeds):
            raise RuntimeError("All feed imports failed; Miniflux bootstrap cannot proceed with zero active seeds.")

        logger.info("miniflux_bootstrap_completed")
    finally:
        bootstrap.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("miniflux_bootstrap_failed error=%s", exc)
        raise SystemExit(1) from exc
