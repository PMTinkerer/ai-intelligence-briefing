"""Tests for daily and weekly email generation."""

from __future__ import annotations

import pytest

from src.generate_email import build_daily_email


def _sample_items():
    return [
        {
            "id": "a1", "title": "Claude Code Channels", "tier": "GAME_CHANGER",
            "layer": 1, "source_name": "Claude Code", "url": "https://example.com/1",
            "what_it_is": "Interact with Claude Code via Telegram",
            "why_it_matters": "Changes the field interaction model completely",
            "expandable_implement": "```bash\nclaude --channels\n```",
            "expandable_learn": "MCP transport layer for messaging platforms",
            "unblocks_project": None,
        },
        {
            "id": "b2", "title": "New /btw command", "tier": "WORTH_YOUR_TIME",
            "layer": 1, "source_name": "Claude Code", "url": "https://example.com/2",
            "what_it_is": "Side questions during streaming",
            "why_it_matters": "Reduces context switching during builds",
            "expandable_implement": None,
            "expandable_learn": "Use /btw to ask questions without interrupting the current task",
            "unblocks_project": None,
        },
        {
            "id": "c3", "title": "Noted item", "tier": "NOTED",
            "layer": 2, "source_name": "Blog", "url": "https://example.com/3",
            "what_it_is": "Something minor",
            "why_it_matters": "Not urgent",
        },
    ]


def _sample_leaderboard():
    return [
        {
            "rank": 1, "title": "MCP Integration", "category": "SKILL_GAP",
            "rationale": "Connective tissue between Claude Code and everything else",
            "first_step": "Connect one MCP server", "time_investment": "30 minutes",
            "days_on_leaderboard": 5,
        },
        {
            "rank": 2, "title": "Autoresearch pattern", "category": "PARADIGM_SHIFT",
            "rationale": "Define scoring function, let agent explore",
            "first_step": "Write OPTIMIZE.md", "time_investment": "2-3 sessions",
            "days_on_leaderboard": 1,
        },
    ]


# ---------------------------------------------------------------------------
# build_daily_email
# ---------------------------------------------------------------------------

def test_daily_email_subject():
    subject, _ = build_daily_email(
        items=_sample_items(),
        leaderboard=_sample_leaderboard(),
        backlog_summary={"total_pending": 3, "oldest_pending": []},
        dropped_counts={"layer_1": 5, "layer_2": 3, "layer_3": 10},
        total_fetched=25,
        report_date="2026-03-23",
        dashboard_url="https://example.com/dashboard",
    )

    assert "AI Intel" in subject
    assert "March 23, 2026" in subject
    assert "1 game-changing" in subject


def test_daily_email_contains_items():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=_sample_leaderboard(),
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={"layer_1": 5},
        total_fetched=10,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "Claude Code Channels" in body
    assert "GAME CHANGER" in body
    assert "WORTH YOUR TIME" in body
    assert "claude --channels" in body


def test_daily_email_contains_leaderboard():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=_sample_leaderboard(),
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={},
        total_fetched=10,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "Top 5 Impact Leaderboard" in body
    assert "MCP Integration" in body
    assert "Autoresearch pattern" in body


def test_daily_email_noted_excluded():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=[],
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={},
        total_fetched=5,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    # NOTED items should not appear in email body as briefing items
    assert "Noted item" not in body


def test_daily_email_filter_transparency():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=[],
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={"layer_1": 5, "layer_2": 3, "layer_3": 10},
        total_fetched=25,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "Reviewed 25 items" in body
    assert "Dropped 18" in body


def test_daily_email_quiet_day():
    subject, body = build_daily_email(
        items=[],
        leaderboard=[],
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={"layer_1": 10},
        total_fetched=10,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "0 items" in subject
    assert "Quiet day" in body


def test_daily_email_project_unblock_subject():
    items = [{
        "id": "u1", "title": "Breezeway API", "tier": "GAME_CHANGER",
        "layer": 1, "source_name": "Test", "url": "https://example.com",
        "what_it_is": "Public API", "why_it_matters": "Unblocks guest comms",
        "expandable_implement": "curl https://api.breezeway.io",
        "expandable_learn": None,
        "unblocks_project": "Guest Comms Intelligence Layer — Breezeway now has a public API",
    }]

    subject, body = build_daily_email(
        items=items, leaderboard=[], backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={}, total_fetched=5, report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "PROJECT UNBLOCK" in subject
    assert "Guest Comms Intelligence Layer" in body


def test_daily_email_backlog_summary():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=[],
        backlog_summary={
            "total_pending": 5,
            "oldest_pending": [
                {"title": "Old item 1", "days_pending": 15},
                {"title": "Old item 2", "days_pending": 12},
            ],
        },
        dropped_counts={},
        total_fetched=10,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "5" in body and "pending" in body
    assert "Old item 1" in body


def test_daily_email_valid_html():
    _, body = build_daily_email(
        items=_sample_items(),
        leaderboard=_sample_leaderboard(),
        backlog_summary={"total_pending": 0, "oldest_pending": []},
        dropped_counts={},
        total_fetched=10,
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert body.startswith("<!DOCTYPE html>")
    assert "</html>" in body
