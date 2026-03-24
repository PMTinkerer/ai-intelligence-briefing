"""Tests for RSS feed fetching, deduplication, and content extraction."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.fetch_feeds import (
    _extract_description,
    _parse_entry_date,
    deduplicate,
    extract_content,
    fetch_all_feeds,
    load_feed_config,
)
from src.state import generate_item_id


# ---------------------------------------------------------------------------
# load_feed_config
# ---------------------------------------------------------------------------

def test_load_feed_config(tmp_path: Path):
    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text(json.dumps({
        "feeds": [
            {"name": "Feed A", "url": "https://a.com/rss", "layer": 1, "enabled": True},
            {"name": "Feed B", "url": "https://b.com/rss", "layer": 2, "enabled": False},
            {"name": "Feed C", "url": "https://c.com/rss", "layer": 3, "enabled": True},
        ]
    }))

    result = load_feed_config(feeds_file)
    assert len(result) == 2
    assert result[0]["name"] == "Feed A"
    assert result[1]["name"] == "Feed C"


def test_load_feed_config_defaults_enabled(tmp_path: Path):
    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text(json.dumps({
        "feeds": [
            {"name": "No Enabled Key", "url": "https://x.com/rss", "layer": 1},
        ]
    }))

    result = load_feed_config(feeds_file)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# fetch_all_feeds (with mocked feedparser)
# ---------------------------------------------------------------------------

def _make_entry(title: str, link: str, hours_ago: float = 1, description: str = "Test desc"):
    pub_time = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "title": title,
        "link": link,
        "summary": description,
        "published_parsed": pub_time.timetuple(),
    }


@patch("src.fetch_feeds.feedparser.parse")
def test_fetch_all_feeds_basic(mock_parse):
    mock_parse.return_value = MagicMock(
        bozo=False,
        entries=[
            _make_entry("Article 1", "https://example.com/1", hours_ago=2),
            _make_entry("Article 2", "https://example.com/2", hours_ago=0.5),
        ],
    )

    feeds = [{"name": "Test", "url": "https://test.com/rss", "layer": 1}]
    items = fetch_all_feeds(feeds, hours_back=24)

    assert len(items) == 2
    assert items[0]["title"] == "Article 1"
    assert items[0]["source_name"] == "Test"
    assert items[0]["layer"] == 1


@patch("src.fetch_feeds.feedparser.parse")
def test_fetch_filters_old_items(mock_parse):
    mock_parse.return_value = MagicMock(
        bozo=False,
        entries=[
            _make_entry("Recent", "https://example.com/1", hours_ago=2),
            _make_entry("Old", "https://example.com/2", hours_ago=48),
        ],
    )

    feeds = [{"name": "Test", "url": "https://test.com/rss", "layer": 1}]
    items = fetch_all_feeds(feeds, hours_back=24)

    assert len(items) == 1
    assert items[0]["title"] == "Recent"


@patch("src.fetch_feeds.feedparser.parse")
def test_fetch_isolates_feed_failures(mock_parse):
    """One feed failing should not block others."""
    def side_effect(url):
        if "bad" in url:
            raise ConnectionError("Network error")
        return MagicMock(
            bozo=False,
            entries=[_make_entry("Good Article", "https://good.com/1")],
        )

    mock_parse.side_effect = side_effect

    feeds = [
        {"name": "Good Feed", "url": "https://good.com/rss", "layer": 1},
        {"name": "Bad Feed", "url": "https://bad.com/rss", "layer": 2},
    ]
    items = fetch_all_feeds(feeds, hours_back=24)

    assert len(items) == 1
    assert items[0]["source_name"] == "Good Feed"


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------

def test_deduplicate_filters_seen(tmp_path: Path):
    seen_path = tmp_path / "seen.json"
    item_id = generate_item_id("https://example.com/1", "Article 1")
    seen_path.write_text(json.dumps({
        "items": {
            item_id: {
                "title": "Article 1",
                "first_seen": "2026-03-22",
                "source_name": "Test",
                "layer": 1,
            }
        },
        "last_run": "2026-03-22T10:00:00+00:00",
    }))

    items = [
        {"title": "Article 1", "url": "https://example.com/1", "source_name": "Test", "layer": 1},
        {"title": "Article 2", "url": "https://example.com/2", "source_name": "Test", "layer": 1},
    ]

    new_items, updated = deduplicate(items, seen_path)

    assert len(new_items) == 1
    assert new_items[0]["title"] == "Article 2"
    assert len(updated["items"]) == 2


def test_deduplicate_cross_layer(tmp_path: Path):
    """Same URL in Layer 2 and Layer 3 should keep Layer 2."""
    seen_path = tmp_path / "seen.json"
    seen_path.write_text(json.dumps({"items": {}, "last_run": None}))

    items = [
        {"title": "Shared Article", "url": "https://example.com/shared", "source_name": "Layer2", "layer": 2},
        {"title": "Shared Article", "url": "https://example.com/shared", "source_name": "Layer3", "layer": 3},
    ]

    new_items, _ = deduplicate(items, seen_path)

    assert len(new_items) == 1
    assert new_items[0]["source_name"] == "Layer2"


def test_deduplicate_prunes_old_entries(tmp_path: Path):
    seen_path = tmp_path / "seen.json"
    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d")
    recent_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")

    seen_path.write_text(json.dumps({
        "items": {
            "old_item": {"title": "Old", "first_seen": old_date, "source_name": "X", "layer": 1},
            "recent_item": {"title": "Recent", "first_seen": recent_date, "source_name": "X", "layer": 1},
        },
        "last_run": None,
    }))

    new_items, updated = deduplicate([], seen_path)

    assert "old_item" not in updated["items"]
    assert "recent_item" in updated["items"]


def test_deduplicate_handles_missing_file(tmp_path: Path):
    seen_path = tmp_path / "nonexistent.json"

    items = [
        {"title": "New Article", "url": "https://example.com/new", "source_name": "Test", "layer": 1},
    ]

    new_items, updated = deduplicate(items, seen_path)

    assert len(new_items) == 1
    assert len(updated["items"]) == 1


# ---------------------------------------------------------------------------
# extract_content
# ---------------------------------------------------------------------------

def test_extract_content_long_description():
    items = [{"description": "A" * 200, "layer": 1, "url": "https://example.com"}]
    result = extract_content(items)
    assert result[0]["content"] == "A" * 200


def test_extract_content_caps_layer3():
    items = [{"description": "A" * 1000, "layer": 3, "url": "https://example.com"}]
    result = extract_content(items)
    assert len(result[0]["content"]) == 500


@patch("src.fetch_feeds.requests.get")
def test_extract_content_fetches_short_descriptions(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = "<html><article><p>Full article content here with lots of detail.</p></article></html>"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    items = [{"description": "Short", "layer": 1, "url": "https://example.com/article"}]
    result = extract_content(items)

    assert "Full article content" in result[0]["content"]
    mock_get.assert_called_once()


@patch("src.fetch_feeds.requests.get")
def test_extract_content_falls_back_on_fetch_error(mock_get):
    mock_get.side_effect = ConnectionError("Timeout")

    items = [{"description": "Short desc", "layer": 1, "url": "https://example.com/article"}]
    result = extract_content(items)

    assert result[0]["content"] == "Short desc"


# ---------------------------------------------------------------------------
# _parse_entry_date
# ---------------------------------------------------------------------------

def test_parse_entry_date_published():
    now = datetime.now(timezone.utc)
    entry = {"published_parsed": now.timetuple()}
    result = _parse_entry_date(entry)
    assert result is not None
    assert result.tzinfo is not None


def test_parse_entry_date_none():
    result = _parse_entry_date({})
    assert result is None


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

def test_extract_description_strips_html():
    entry = {"summary": "<p>Hello <b>world</b></p>"}
    result = _extract_description(entry)
    assert result == "Hello world"


def test_extract_description_prefers_summary():
    entry = {
        "summary": "Summary text",
        "content": [{"value": "Content text"}],
    }
    result = _extract_description(entry)
    assert result == "Summary text"


def test_extract_description_falls_back_to_content():
    entry = {
        "summary": "",
        "content": [{"value": "Content text"}],
    }
    result = _extract_description(entry)
    assert result == "Content text"
