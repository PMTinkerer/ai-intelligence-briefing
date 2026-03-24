"""Tests for dashboard generation."""

from __future__ import annotations

import json
from pathlib import Path

from src.generate_dashboard import build_dashboard, update_briefings_data


def test_update_briefings_appends(tmp_path: Path):
    path = tmp_path / "briefings.json"
    path.write_text("[]")

    update_briefings_data(
        items=[{"title": "Test", "tier": "GAME_CHANGER"}],
        leaderboard=[{"rank": 1, "title": "X"}],
        backlog_summary={"total_pending": 0},
        dropped_counts={"layer_1": 5},
        total_fetched=10,
        report_date="2026-03-23",
        briefings_path=path,
    )

    data = json.loads(path.read_text())
    assert len(data) == 1
    assert data[0]["date"] == "2026-03-23"
    assert len(data[0]["items"]) == 1


def test_update_briefings_no_overwrite(tmp_path: Path):
    path = tmp_path / "briefings.json"
    path.write_text(json.dumps([
        {"date": "2026-03-22", "items": [], "leaderboard": [],
         "backlog_summary": {}, "dropped_counts": {}, "total_fetched": 0}
    ]))

    update_briefings_data(
        items=[], leaderboard=[], backlog_summary={},
        dropped_counts={}, total_fetched=0,
        report_date="2026-03-23", briefings_path=path,
    )

    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[0]["date"] == "2026-03-23"
    assert data[1]["date"] == "2026-03-22"


def test_build_dashboard_returns_html(tmp_path: Path):
    briefings = tmp_path / "briefings.json"
    backlog = tmp_path / "backlog.json"
    leaderboard = tmp_path / "leaderboard.json"

    briefings.write_text(json.dumps([{
        "date": "2026-03-23",
        "items": [{"title": "Test", "tier": "GAME_CHANGER", "layer": 1,
                   "source_name": "Test", "url": "https://example.com",
                   "what_it_is": "A test"}],
        "leaderboard": [],
        "backlog_summary": {},
        "dropped_counts": {},
        "total_fetched": 5,
    }]))
    backlog.write_text(json.dumps({"items": []}))
    leaderboard.write_text(json.dumps({"leaderboard": [
        {"rank": 1, "title": "MCP", "category": "SKILL_GAP",
         "rationale": "Important", "first_step": "Try it",
         "time_investment": "30m", "days_on_leaderboard": 3}
    ]}))

    result = build_dashboard(briefings, backlog, leaderboard)

    assert "<!DOCTYPE html>" in result
    assert "AI Intelligence Briefing" in result
    assert "Chart" in result
    assert "MCP" in result
    assert "Test" in result


def test_dashboard_backlog_has_toggle_checkboxes(tmp_path: Path):
    briefings = tmp_path / "briefings.json"
    backlog = tmp_path / "backlog.json"
    leaderboard = tmp_path / "leaderboard.json"

    briefings.write_text("[]")
    backlog.write_text(json.dumps({"items": [
        {"id": "abc123", "title": "Try MCP", "tier": "GAME_CHANGER",
         "status": "pending", "date_added": "2026-03-20", "days_pending": 3,
         "expandable_implement": "Install MCP"},
    ]}))
    leaderboard.write_text(json.dumps({"leaderboard": []}))

    result = build_dashboard(briefings, backlog, leaderboard)

    # Verify checkbox and toggle infrastructure
    assert 'type="checkbox"' in result
    assert "toggleBacklogItem" in result
    assert "localStorage" in result
    assert "clearCompleted" in result
    assert "clear-completed-btn" in result
    assert "pruneBacklogStorage" in result
    assert "backlog-counter" in result
