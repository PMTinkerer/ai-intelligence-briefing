"""Tests for AI classification engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.classify import classify_all, classify_layer, generate_leaderboard, _fallback_leaderboard


def _mock_response(content: dict, input_tokens: int = 500, output_tokens: int = 200):
    """Create a mock Anthropic API response."""
    resp = MagicMock()
    resp.content = [MagicMock(text=json.dumps(content))]
    resp.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return resp


# ---------------------------------------------------------------------------
# classify_layer
# ---------------------------------------------------------------------------

@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger")
@patch("src.classify.can_spend", return_value=True)
def test_classify_layer_basic(mock_can_spend, mock_load, mock_save, mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    mock_client.messages.create.return_value = _mock_response({
        "items": [
            {
                "id": "abc123",
                "tier": "GAME_CHANGER",
                "what_it_is": "A new feature",
                "why_it_matters": "It changes everything",
                "expandable_implement": "```bash\nclaude --channels\n```",
                "expandable_learn": "Read the docs",
                "unblocks_project": None,
            },
            {
                "id": "def456",
                "tier": "DROPPED",
                "what_it_is": "A bug fix",
                "why_it_matters": "",
                "expandable_implement": None,
                "expandable_learn": None,
                "unblocks_project": None,
            },
        ]
    })

    items = [
        {"id": "abc123", "title": "Channels Launch", "url": "https://example.com/1",
         "source_name": "Claude Code", "layer": 1, "content": "Full content here"},
        {"id": "def456", "title": "Bug Fix", "url": "https://example.com/2",
         "source_name": "Claude Code", "layer": 1, "content": "Fixed a bug"},
    ]

    result = classify_layer(items, 1, "Business context here", [], "test-key")

    assert len(result["items"]) == 1
    assert result["items"][0]["tier"] == "GAME_CHANGER"
    assert result["dropped_count"] == 1


@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger")
@patch("src.classify.can_spend", return_value=True)
def test_classify_layer_handles_markdown_fences(mock_cs, mock_ll, mock_sl, mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Response wrapped in markdown code fences
    resp = MagicMock()
    resp.content = [MagicMock(text='```json\n{"items": [{"id": "x1", "tier": "NOTED", "what_it_is": "test", "why_it_matters": "test"}]}\n```')]
    resp.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_client.messages.create.return_value = resp

    items = [{"id": "x1", "title": "Test", "url": "https://x.com", "layer": 1, "content": "..."}]
    result = classify_layer(items, 1, "", [], "test-key")

    # NOTED items are surfaced (not dropped)
    assert len(result["items"]) == 1
    assert result["items"][0]["tier"] == "NOTED"


def test_classify_layer_empty_items():
    result = classify_layer([], 1, "", [], "test-key")
    assert result["items"] == []
    assert result["dropped_count"] == 0


@patch("src.classify.can_spend", return_value=False)
@patch("src.classify.load_ledger")
def test_classify_layer_budget_exceeded(mock_load, mock_can_spend):
    items = [{"id": "a", "title": "X", "url": "https://x.com", "layer": 1, "content": "..."}]
    result = classify_layer(items, 1, "", [], "test-key")
    assert result["items"] == []
    assert result["dropped_count"] == 1


@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger")
@patch("src.classify.can_spend", return_value=True)
def test_classify_layer_api_failure(mock_cs, mock_ll, mock_sl, mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("API Error")

    items = [{"id": "a", "title": "X", "url": "https://x.com", "layer": 1, "content": "..."}]
    result = classify_layer(items, 1, "", [], "test-key")

    assert result["items"] == []
    assert result["dropped_count"] == 1


# ---------------------------------------------------------------------------
# classify_all
# ---------------------------------------------------------------------------

@patch("src.classify.classify_layer")
def test_classify_all_groups_by_layer(mock_classify):
    mock_classify.side_effect = [
        {"items": [{"id": "1", "tier": "GAME_CHANGER", "layer": 1}], "dropped_count": 2},
        {"items": [{"id": "2", "tier": "WORTH_YOUR_TIME", "layer": 2}], "dropped_count": 1},
        {"items": [], "dropped_count": 3},
    ]

    items = [
        {"layer": 1, "id": "a"}, {"layer": 1, "id": "b"}, {"layer": 1, "id": "c"},
        {"layer": 2, "id": "d"}, {"layer": 2, "id": "e"},
        {"layer": 3, "id": "f"}, {"layer": 3, "id": "g"}, {"layer": 3, "id": "h"},
    ]

    classified, dropped = classify_all(items, "ctx", [], "key")

    assert len(classified) == 2
    assert dropped == {"layer_1": 2, "layer_2": 1, "layer_3": 3}
    assert mock_classify.call_count == 3


@patch("src.classify.classify_layer")
def test_classify_all_layer_failure_isolated(mock_classify):
    """One layer failing should not block others."""
    mock_classify.side_effect = [
        {"items": [{"id": "1", "tier": "GAME_CHANGER", "layer": 1}], "dropped_count": 0},
        {"items": [], "dropped_count": 5},  # Layer 2 "failed" (returned empty)
        {"items": [{"id": "3", "tier": "NOTED", "layer": 3}], "dropped_count": 2},
    ]

    items = [{"layer": 1}, {"layer": 2}, {"layer": 2}, {"layer": 2},
             {"layer": 2}, {"layer": 2}, {"layer": 3}, {"layer": 3}, {"layer": 3}]

    classified, dropped = classify_all(items, "ctx", [], "key")

    assert len(classified) == 2  # Layer 1 + Layer 3 items


# ---------------------------------------------------------------------------
# generate_leaderboard
# ---------------------------------------------------------------------------

@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger")
@patch("src.classify.can_spend", return_value=True)
def test_generate_leaderboard_basic(mock_cs, mock_ll, mock_sl, mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    mock_client.messages.create.return_value = _mock_response({
        "leaderboard": [
            {"rank": 1, "title": "MCP Integration", "category": "SKILL_GAP",
             "rationale": "Important", "first_step": "Do it", "time_investment": "30 min",
             "days_on_leaderboard": 1},
        ],
        "changes_today": ["NEW: MCP Integration entered at #1"],
    })

    result = generate_leaderboard(
        classified_items=[{"title": "X", "tier": "GAME_CHANGER", "what_it_is": "..."}],
        previous_leaderboard={"leaderboard": [], "changes_today": []},
        backlog_items=[],
        business_context="ctx",
        blocked_projects=[],
        api_key="key",
    )

    assert len(result["leaderboard"]) == 1
    assert result["leaderboard"][0]["title"] == "MCP Integration"


@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger")
@patch("src.classify.can_spend", return_value=True)
def test_generate_leaderboard_fallback_on_failure(mock_cs, mock_ll, mock_sl, mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("API Error")

    previous = {
        "leaderboard": [
            {"rank": 1, "title": "Previous Item", "days_on_leaderboard": 5},
        ],
        "changes_today": [],
    }

    result = generate_leaderboard([], previous, [], "ctx", [], "key")

    assert result["leaderboard"][0]["title"] == "Previous Item"
    assert result["leaderboard"][0]["days_on_leaderboard"] == 6
    assert "failed" in result["changes_today"][0].lower()


# ---------------------------------------------------------------------------
# _fallback_leaderboard
# ---------------------------------------------------------------------------

def test_fallback_leaderboard_increments_days():
    prev = {
        "leaderboard": [
            {"rank": 1, "title": "A", "days_on_leaderboard": 3},
            {"rank": 2, "title": "B", "days_on_leaderboard": 7},
        ],
        "changes_today": [],
    }

    result = _fallback_leaderboard(prev)

    assert result["leaderboard"][0]["days_on_leaderboard"] == 4
    assert result["leaderboard"][1]["days_on_leaderboard"] == 8


def test_fallback_leaderboard_empty():
    result = _fallback_leaderboard({"leaderboard": [], "changes_today": []})
    assert result["leaderboard"] == []
