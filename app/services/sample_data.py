from __future__ import annotations

import json
from pathlib import Path


def load_sample_entries(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read sample data file at {path}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Sample data file at {path} is not valid JSON: {exc}") from exc

    if isinstance(payload, dict):
        entries = payload.get("entries")
    else:
        entries = payload

    if not isinstance(entries, list):
        raise ValueError("Sample data JSON must be a list or an object containing an 'entries' list.")

    normalized: list[dict] = []
    for index, item in enumerate(entries):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            raise ValueError(f"Sample entry at index {index} is not an object.")

    return normalized
