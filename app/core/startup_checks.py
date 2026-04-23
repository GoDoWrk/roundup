from __future__ import annotations

from typing import Literal

from app.core.config import Settings, get_settings


def run_startup_checks(mode: Literal["api", "worker"], settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    issues = resolved.validate_startup(mode)
    if not issues:
        return

    details = "\n".join(f"- {issue}" for issue in issues)
    raise RuntimeError(f"Startup checks failed for {mode} mode:\n{details}")
