"""Tests for adoption backlog management."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.backlog import get_backlog_stats, mark_adopted, update_backlog


def _make_classified_item(item_id: str, tier: str, title: str = "Test",
                          implement: str = "```bash\necho hi\n```") -> dict:
    return {
        "id": item_id,
        "title": title,
        "url": f"https://example.com/{item_id}",
        "tier": tier,
        "layer": 1,
        "expandable_implement": implement,
    }


# ---------------------------------------------------------------------------
# update_backlog
# ---------------------------------------------------------------------------

def test_update_adds_actionable_items(tmp_path: Path):
    path = tmp_path / "backlog.json"
    path.write_text(json.dumps({"items": [], "stats": {}}))

    items = [
        _make_classified_item("a1", "GAME_CHANGER"),
        _make_classified_item("b2", "WORTH_YOUR_TIME"),
        _make_classified_item("c3", "NOTED"),  # Should NOT be added
        _make_classified_item("d4", "GAME_CHANGER", implement=""),  # No artifact, skip
    ]

    summary = update_backlog(items, path)

    assert summary["new_this_run"] == 2
    assert summary["total_pending"] == 2

    data = json.loads(path.read_text())
    assert len(data["items"]) == 2


def test_update_no_duplicates(tmp_path: Path):
    path = tmp_path / "backlog.json"
    path.write_text(json.dumps({
        "items": [{
            "id": "a1", "title": "Existing", "source_url": "...", "tier": "GAME_CHANGER",
            "layer": 1, "expandable_implement": "...", "status": "pending",
            "date_added": "2026-03-20", "date_adopted": None, "date_archived": None,
        }],
        "stats": {},
    }))

    items = [_make_classified_item("a1", "GAME_CHANGER")]
    summary = update_backlog(items, path)

    assert summary["new_this_run"] == 0
    data = json.loads(path.read_text())
    assert len(data["items"]) == 1


def test_update_auto_archives_old_items(tmp_path: Path):
    path = tmp_path / "backlog.json"
    old_date = (datetime.now(timezone.utc) - timedelta(days=25)).strftime("%Y-%m-%d")
    path.write_text(json.dumps({
        "items": [{
            "id": "old1", "title": "Old Item", "source_url": "...", "tier": "WORTH_YOUR_TIME",
            "layer": 1, "expandable_implement": "...", "status": "pending",
            "date_added": old_date, "date_adopted": None, "date_archived": None,
        }],
        "stats": {},
    }))

    summary = update_backlog([], path)

    assert summary["archived_this_run"] == 1
    data = json.loads(path.read_text())
    assert data["items"][0]["status"] == "archived"
    assert data["items"][0]["date_archived"] is not None


def test_update_computes_days_pending(tmp_path: Path):
    path = tmp_path / "backlog.json"
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    path.write_text(json.dumps({
        "items": [{
            "id": "r1", "title": "Recent", "source_url": "...", "tier": "GAME_CHANGER",
            "layer": 1, "expandable_implement": "...", "status": "pending",
            "date_added": five_days_ago, "date_adopted": None, "date_archived": None,
        }],
        "stats": {},
    }))

    summary = update_backlog([], path)

    data = json.loads(path.read_text())
    assert data["items"][0]["days_pending"] == 5


def test_update_handles_missing_file(tmp_path: Path):
    path = tmp_path / "nonexistent.json"
    items = [_make_classified_item("new1", "GAME_CHANGER")]
    summary = update_backlog(items, path)

    assert summary["new_this_run"] == 1
    assert path.exists()


# ---------------------------------------------------------------------------
# mark_adopted
# ---------------------------------------------------------------------------

def test_mark_adopted_success(tmp_path: Path):
    path = tmp_path / "backlog.json"
    path.write_text(json.dumps({
        "items": [{
            "id": "x1", "title": "Test", "source_url": "...", "tier": "GAME_CHANGER",
            "layer": 1, "expandable_implement": "...", "status": "pending",
            "date_added": "2026-03-20", "date_adopted": None, "date_archived": None,
        }],
        "stats": {},
    }))

    assert mark_adopted("x1", path) is True

    data = json.loads(path.read_text())
    assert data["items"][0]["status"] == "adopted"
    assert data["items"][0]["date_adopted"] is not None


def test_mark_adopted_not_found(tmp_path: Path):
    path = tmp_path / "backlog.json"
    path.write_text(json.dumps({"items": [], "stats": {}}))

    assert mark_adopted("nonexistent", path) is False


# ---------------------------------------------------------------------------
# get_backlog_stats
# ---------------------------------------------------------------------------

def test_get_backlog_stats(tmp_path: Path):
    path = tmp_path / "backlog.json"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path.write_text(json.dumps({
        "items": [
            {"id": "1", "status": "pending", "date_added": today},
            {"id": "2", "status": "adopted", "date_adopted": today},
            {"id": "3", "status": "archived", "date_archived": today},
            {"id": "4", "status": "pending", "date_added": today},
        ],
        "stats": {},
    }))

    stats = get_backlog_stats(path)

    assert stats["total_pending"] == 2
    assert stats["total_adopted"] == 1
    assert stats["total_archived"] == 1
    assert stats["adoption_rate_4w"] == 0.5  # 1 adopted / (1 adopted + 1 archived)
