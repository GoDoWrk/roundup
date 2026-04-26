from __future__ import annotations

from app.services.normalizer import extract_image_url, normalize_miniflux_entry


def test_extract_image_url_prefers_explicit_image_field() -> None:
    entry = {
        "image_url": "https://cdn.example.com/lead.jpg",
        "media_thumbnail": [{"url": "https://cdn.example.com/thumb.jpg"}],
    }

    assert extract_image_url(entry) == "https://cdn.example.com/lead.jpg"


def test_extract_image_url_reads_feedparser_media_fields() -> None:
    entry = {
        "media_thumbnail": [{"url": "https://cdn.example.com/thumb.jpg"}],
        "media_content": [{"url": "https://cdn.example.com/media.jpg", "type": "image/jpeg"}],
    }

    assert extract_image_url(entry) == "https://cdn.example.com/thumb.jpg"


def test_extract_image_url_ignores_non_image_media_content() -> None:
    entry = {
        "media_content": [
            {"url": "https://cdn.example.com/video.mp4", "type": "video/mp4"},
            {"url": "https://cdn.example.com/photo.jpg", "medium": "image"},
        ]
    }

    assert extract_image_url(entry) == "https://cdn.example.com/photo.jpg"


def test_extract_image_url_reads_miniflux_image_enclosures() -> None:
    entry = {
        "enclosures": [
            {"url": "https://cdn.example.com/audio.mp3", "mime_type": "audio/mpeg"},
            {"url": "https://cdn.example.com/photo.webp", "mime_type": "image/webp"},
        ]
    }

    assert extract_image_url(entry) == "https://cdn.example.com/photo.webp"


def test_extract_image_url_accepts_image_url_enclosure_with_octet_stream_mime() -> None:
    entry = {
        "enclosures": [
            {"url": "https://cdn.example.com/download", "mime_type": "application/octet-stream"},
            {"url": "https://i.guim.co.uk/img/media/example/master/2336.jpg?width=700", "mime_type": "application/octet-stream"},
        ]
    }

    assert extract_image_url(entry) == "https://i.guim.co.uk/img/media/example/master/2336.jpg?width=700"


def test_extract_image_url_reads_html_metadata_before_img_fallback() -> None:
    content = """
    <html>
      <head><meta property="og:image" content="https://cdn.example.com/open-graph.jpg"></head>
      <body><img src="https://cdn.example.com/body.jpg"></body>
    </html>
    """

    assert extract_image_url({}, content) == "https://cdn.example.com/open-graph.jpg"


def test_extract_image_url_filters_invalid_blank_and_duplicate_urls() -> None:
    entry = {
        "image_url": "   ",
        "thumbnail_url": "javascript:alert(1)",
        "media_thumbnail": [
            {"url": "https://cdn.example.com/thumb.jpg#fragment"},
            {"url": "https://cdn.example.com/thumb.jpg"},
        ],
    }

    assert extract_image_url(entry) == "https://cdn.example.com/thumb.jpg"


def test_extract_image_url_falls_back_to_none_for_missing_or_malformed_images() -> None:
    assert extract_image_url({"image": object(), "enclosures": {"url": "https://cdn.example.com/file.zip"}}) is None


def test_normalize_miniflux_entry_populates_image_url() -> None:
    normalized = normalize_miniflux_entry(
        {
            "id": 1,
            "title": "Transit Plan Advances",
            "url": "https://example.com/story",
            "published_at": "2026-04-22T10:00:00Z",
            "content": "Body",
            "feed": {"title": "Example Feed"},
            "enclosures": [{"url": "https://cdn.example.com/story.jpg", "mime_type": "image/jpeg"}],
        }
    )

    assert normalized.image_url == "https://cdn.example.com/story.jpg"
