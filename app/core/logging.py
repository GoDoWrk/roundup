from __future__ import annotations

import logging
import re
from collections.abc import Mapping

from app.core.config import get_settings


SECRET_FIELD_NAMES = {
    "admin_password",
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "miniflux_api_key",
    "miniflux_api_token",
    "password",
    "secret",
    "token",
    "x-auth-token",
    "x_auth_token",
}

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|auth[_-]?token|authorization|miniflux[_-]?api[_-]?(?:key|token)|password|secret|token)"
    r"(\s*[=:]\s*)"
    r"([^,\s&]+)"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")


def redact_secrets(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: "<redacted>" if str(key).strip().lower().replace("-", "_") in SECRET_FIELD_NAMES else redact_secrets(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)

    if isinstance(value, list):
        return [redact_secrets(item) for item in value]

    if not isinstance(value, str):
        return value

    redacted = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", value)
    return SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", redacted)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.msg)
        if record.args:
            record.args = redact_secrets(record.args)
        return True


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    redaction_filter = SecretRedactionFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(redaction_filter)
    for handler in root_logger.handlers:
        handler.addFilter(redaction_filter)
