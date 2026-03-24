"""Integration test: full pipeline with mocked external services."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.backlog import update_backlog
from src.classify import classify_all, generate_leaderboard
from src.fetch_feeds import deduplicate, extract_content, fetch_all_feeds, load_feed_config
from src.generate_dashboard import build_dashboard, update_briefings_data
from src.generate_email import build_daily_email
from src.state import load_json_or_default


def _mock_feed_response():
    """Create a mock feedparser response with test items."""
    now = datetime.now(timezone.utc)
    return MagicMock(
        bozo=False,
        entries=[
            {
                "title": "Claude Code Channels Launch",
                "link": "https://example.com/channels",
                "summary": "Claude Code now supports interaction via Telegram and Discord through MCP channel servers.",
                "published_parsed": now.timetuple(),
            },
            {
                "title": "Minor color fix in terminal",
                "link": "https://example.com/color-fix",
                "summary": "Fixed washed-out orange in terminals without truecolor support.",
                "published_parsed": now.timetuple(),
            },
        ],
    )


def _mock_classify_response(items):
    """Create a mock classification response."""
    classified = []
    for item in items:
        if "Channels" in item.get("title", ""):
            classified.append({
                "id": item["id"],
                "tier": "GAME_CHANGER",
                "what_it_is": "Claude Code via Telegram",
                "why_it_matters": "Field interaction paradigm shift",
                "expandable_implement": "```bash\nclaude --channels\n```",
                "expandable_learn": "MCP transport layer",
                "unblocks_project": None,
            })
        else:
            classified.append({
                "id": item["id"],
                "tier": "DROPPED",
                "what_it_is": "Bug fix",
                "why_it_matters": "",
            })
    return {"items": classified, "dropped_count": 1}


@patch("src.classify.anthropic.Anthropic")
@patch("src.classify.save_ledger")
@patch("src.classify.load_ledger", return_value={"month": "2026-03", "entries": []})
@patch("src.classify.can_spend", return_value=True)
@patch("src.fetch_feeds.feedparser.parse")
def test_full_pipeline(mock_parse, mock_can_spend, mock_load, mock_save, mock_anthropic, tmp_path: Path):
    """Test the complete pipeline from fetch to email generation."""

    # Setup mocks
    mock_parse.return_value = _mock_feed_response()

    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Classification mock - return based on input
    def classify_side_effect(**kwargs):
        content = kwargs.get("messages", [{}])[0].get("content", "")
        if "Classify" in content or "classify" in content or "items" in content.lower():
            items_json = json.loads(content.split("items:\n\n")[1]) if "items:\n\n" in content else []
            result = {"items": []}
            for item in items_json:
                if "Channels" in item.get("title", ""):
                    result["items"].append({
                        "id": item["id"],
                        "tier": "GAME_CHANGER",
                        "what_it_is": "Telegram integration",
                        "why_it_matters": "Field paradigm shift",
                        "expandable_implement": "claude --channels",
                        "expandable_learn": "MCP transport",
                        "unblocks_project": None,
                    })
                else:
                    result["items"].append({"id": item["id"], "tier": "DROPPED", "what_it_is": "x", "why_it_matters": ""})
        else:
            # Leaderboard call
            result = {
                "leaderboard": [
                    {"rank": 1, "title": "MCP Integration", "category": "SKILL_GAP",
                     "rationale": "Connective tissue", "first_step": "Try it",
                     "time_investment": "30m", "days_on_leaderboard": 1}
                ],
                "changes_today": ["NEW: MCP entered"],
            }

        resp = MagicMock()
        resp.content = [MagicMock(text=json.dumps(result))]
        resp.usage = MagicMock(input_tokens=100, output_tokens=50)
        return resp

    mock_client.messages.create.side_effect = classify_side_effect

    # Setup temp data files
    seen_path = tmp_path / "seen.json"
    seen_path.write_text(json.dumps({"items": {}, "last_run": None}))

    feeds_path = tmp_path / "feeds.json"
    feeds_path.write_text(json.dumps({
        "feeds": [
            {"name": "Test Feed", "url": "https://test.com/rss", "layer": 1, "enabled": True},
        ]
    }))

    backlog_path = tmp_path / "backlog.json"
    backlog_path.write_text(json.dumps({"items": [], "stats": {}}))

    briefings_path = tmp_path / "briefings.json"
    briefings_path.write_text("[]")

    leaderboard_path = tmp_path / "leaderboard.json"
    leaderboard_path.write_text(json.dumps({"leaderboard": [], "changes_today": []}))

    # ---- Run pipeline steps ----

    # 1. Fetch
    feeds = load_feed_config(feeds_path)
    raw_items = fetch_all_feeds(feeds, hours_back=24)
    assert len(raw_items) == 2

    # 2. Dedup
    new_items, updated_seen = deduplicate(raw_items, seen_path)
    assert len(new_items) == 2

    # 3. Content extraction
    new_items = extract_content(new_items)
    assert all("content" in item for item in new_items)

    # 4. Classify
    classified, dropped = classify_all(new_items, "Business context", [], "test-key")

    # 5. Leaderboard
    prev = load_json_or_default(leaderboard_path, {"leaderboard": []})
    lb = generate_leaderboard(classified, prev, [], "ctx", [], "test-key")

    # 6. Backlog
    summary = update_backlog(classified, backlog_path)

    # 7. Email
    subject, html_body = build_daily_email(
        items=classified,
        leaderboard=lb.get("leaderboard", []),
        backlog_summary=summary,
        dropped_counts=dropped,
        total_fetched=len(raw_items),
        report_date="2026-03-23",
        dashboard_url="https://example.com",
    )

    assert "AI Intel" in subject
    assert "<!DOCTYPE html>" in html_body

    # 8. Dashboard data
    update_briefings_data(
        classified, lb.get("leaderboard", []),
        summary, dropped, len(raw_items),
        "2026-03-23", briefings_path,
    )

    briefings = json.loads(briefings_path.read_text())
    assert len(briefings) == 1
    assert briefings[0]["date"] == "2026-03-23"

    # 9. Dashboard HTML
    html_dashboard = build_dashboard(briefings_path, backlog_path, leaderboard_path)
    assert "AI Intelligence Briefing" in html_dashboard
