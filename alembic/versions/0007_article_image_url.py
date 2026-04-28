"""add article image url

Revision ID: 0007_article_image_url
Revises: 0006_article_src_idx_hardening
Create Date: 2026-04-25 00:00:00.000000
"""

from typing import Sequence, Union
import re
from html import unescape
from urllib.parse import urlparse, urlunparse

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_article_image_url"
down_revision: Union[str, None] = "0006_article_src_idx_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _valid_image_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse(parsed._replace(fragment=""))


def _append_candidate(candidates: list[str], value: object) -> None:
    image_url = _valid_image_url(value)
    if image_url is not None:
        candidates.append(image_url)


def extract_image_url(entry: dict, content: str = "") -> str | None:
    candidates: list[str] = []
    for key in ("image_url", "thumbnail_url", "lead_image_url"):
        _append_candidate(candidates, entry.get(key))

    image_value = entry.get("image")
    if isinstance(image_value, dict):
        _append_candidate(candidates, image_value.get("url") or image_value.get("href") or image_value.get("src"))
    else:
        _append_candidate(candidates, image_value)

    for key in ("metadata", "meta", "article_metadata", "open_graph", "opengraph", "twitter"):
        nested = entry.get(key)
        if not isinstance(nested, dict):
            continue
        for image_key in ("image", "image_url", "thumbnail", "thumbnail_url", "lead_image_url", "og:image", "twitter:image"):
            value = nested.get(image_key)
            if isinstance(value, dict):
                _append_candidate(candidates, value.get("url") or value.get("href") or value.get("src"))
            else:
                _append_candidate(candidates, value)

    meta_pattern = re.compile(r"<meta\b(?P<attrs>[^>]*?)>", re.IGNORECASE)
    attr_pattern = re.compile(r"([A-Za-z_:.-]+)\s*=\s*(['\"])(.*?)\2", re.IGNORECASE | re.DOTALL)
    for match in meta_pattern.finditer(content or ""):
        attrs = {name.lower(): unescape(value.strip()) for name, _, value in attr_pattern.findall(match.group("attrs"))}
        name = attrs.get("property") or attrs.get("name")
        if name and name.lower() in {"og:image", "twitter:image", "twitter:image:src"}:
            _append_candidate(candidates, attrs.get("content"))

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        return candidate
    return None


def upgrade() -> None:
    op.add_column("articles", sa.Column("image_url", sa.Text(), nullable=True))

    bind = op.get_bind()
    articles = sa.table(
        "articles",
        sa.column("id", sa.Integer),
        sa.column("raw_payload", sa.JSON),
        sa.column("content_text", sa.Text),
        sa.column("image_url", sa.Text),
    )
    rows = list(bind.execute(sa.select(articles.c.id, articles.c.raw_payload, articles.c.content_text)).all())
    for row in rows:
        raw_payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        image_url = extract_image_url(raw_payload, str(row.content_text or ""))
        if image_url is not None:
            bind.execute(articles.update().where(articles.c.id == row.id).values(image_url=image_url))


def downgrade() -> None:
    op.drop_column("articles", "image_url")
