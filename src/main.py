"""Daily orchestrator: fetch → dedup → classify → leaderboard → backlog → email → dashboard."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths relative to project root
_CONFIG_DIR = Path("config")
_DATA_DIR = Path("data")
_DOCS_DIR = Path("docs")


def run_daily_briefing(dry_run: bool = False, layer: int | None = None) -> None:
    """Run the full daily briefing pipeline.

    Args:
        dry_run: If True, skip state changes and email sending.
        layer: If set, only process this layer (1, 2, or 3).
    """
    from src.backlog import update_backlog
    from src.classify import classify_all, generate_leaderboard
    from src.config import ANTHROPIC_API_KEY, BRIEFING_RECIPIENTS, DASHBOARD_URL
    from src.fetch_feeds import deduplicate, extract_content, fetch_all_feeds, load_feed_config
    from src.generate_dashboard import build_dashboard, update_briefings_data
    from src.generate_email import build_daily_email
    from src.state import load_json_or_default, save_json

    report_date = date.today().isoformat()
    logger.info("Starting daily briefing for %s (dry_run=%s, layer=%s)", report_date, dry_run, layer)

    # -------------------------------------------------------------------------
    # 1. Load config
    # -------------------------------------------------------------------------
    feeds_path = _CONFIG_DIR / "feeds.json"
    context_path = _CONFIG_DIR / "business_context.md"
    blocked_path = _CONFIG_DIR / "blocked_projects.json"

    feeds = load_feed_config(feeds_path)
    if layer:
        feeds = [f for f in feeds if f["layer"] == layer]
        logger.info("Filtered to Layer %d: %d feeds", layer, len(feeds))

    business_context = context_path.read_text(encoding="utf-8")
    blocked_data = load_json_or_default(blocked_path, {"blocked_projects": []})
    blocked_projects = blocked_data.get("blocked_projects", [])

    # -------------------------------------------------------------------------
    # 2. Fetch feeds
    # -------------------------------------------------------------------------
    raw_items = fetch_all_feeds(feeds, hours_back=24)
    total_fetched = len(raw_items)

    if not raw_items:
        logger.info("No items fetched — generating quiet day briefing")

    # -------------------------------------------------------------------------
    # 3. Deduplicate
    # -------------------------------------------------------------------------
    seen_path = _DATA_DIR / "seen_items.json"
    new_items, updated_seen = deduplicate(raw_items, seen_path)

    # -------------------------------------------------------------------------
    # 4. Extract content for short descriptions
    # -------------------------------------------------------------------------
    new_items = extract_content(new_items)

    # -------------------------------------------------------------------------
    # 5. Classify (3 layers)
    # -------------------------------------------------------------------------
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — cannot classify")
        classified_items, dropped_counts = [], {}
    elif new_items:
        classified_items, dropped_counts = classify_all(
            new_items, business_context, blocked_projects, ANTHROPIC_API_KEY
        )
    else:
        classified_items, dropped_counts = [], {}

    # -------------------------------------------------------------------------
    # 6. Generate leaderboard
    # -------------------------------------------------------------------------
    leaderboard_path = _DATA_DIR / "leaderboard.json"
    previous_leaderboard = load_json_or_default(leaderboard_path, {"leaderboard": [], "changes_today": []})
    backlog_path = _DATA_DIR / "backlog.json"
    backlog_data = load_json_or_default(backlog_path, {"items": []})

    if ANTHROPIC_API_KEY:
        leaderboard_result = generate_leaderboard(
            classified_items, previous_leaderboard,
            backlog_data.get("items", []),
            business_context, blocked_projects, ANTHROPIC_API_KEY
        )
    else:
        leaderboard_result = previous_leaderboard

    # -------------------------------------------------------------------------
    # 7. Update backlog
    # -------------------------------------------------------------------------
    backlog_summary = update_backlog(classified_items, backlog_path) if not dry_run else {
        "total_pending": 0, "total_adopted": 0, "total_archived": 0,
        "adoption_rate_4w": 0.0, "new_this_run": 0, "archived_this_run": 0, "oldest_pending": [],
    }

    # -------------------------------------------------------------------------
    # 8. Generate email
    # -------------------------------------------------------------------------
    subject, email_html = build_daily_email(
        items=classified_items,
        leaderboard=leaderboard_result.get("leaderboard", []),
        backlog_summary=backlog_summary,
        dropped_counts=dropped_counts,
        total_fetched=total_fetched,
        report_date=report_date,
        dashboard_url=DASHBOARD_URL,
    )

    # -------------------------------------------------------------------------
    # 9. Update dashboard data
    # -------------------------------------------------------------------------
    briefings_path = _DATA_DIR / "briefings.json"
    if not dry_run:
        update_briefings_data(
            classified_items, leaderboard_result.get("leaderboard", []),
            backlog_summary, dropped_counts, total_fetched,
            report_date, briefings_path,
        )

        # Save leaderboard state
        leaderboard_result["date"] = report_date
        save_json(leaderboard_path, leaderboard_result)

        # Save seen items
        save_json(seen_path, updated_seen)

        # Regenerate dashboard HTML
        dashboard_html = build_dashboard(briefings_path, backlog_path, leaderboard_path)
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)
        (_DOCS_DIR / "index.html").write_text(dashboard_html, encoding="utf-8")
        logger.info("Dashboard saved → %s", _DOCS_DIR / "index.html")

    # -------------------------------------------------------------------------
    # 10. Send or print
    # -------------------------------------------------------------------------
    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — {report_date}")
        print(f"{'='*60}")
        print(f"Fetched: {total_fetched} items")
        print(f"New (after dedup): {len(new_items)}")
        print(f"Classified: {len(classified_items)} items surfaced")
        print(f"Dropped: {dropped_counts}")
        print(f"Leaderboard: {len(leaderboard_result.get('leaderboard', []))} entries")
        print(f"Subject: {subject}")
        print(f"Email HTML: {len(email_html)} bytes")

        if classified_items:
            print(f"\nSurfaced items:")
            for item in classified_items:
                print(f"  [{item.get('tier')}] {item.get('title')} ({item.get('source_name')})")

        if leaderboard_result.get("changes_today"):
            print(f"\nLeaderboard changes: {leaderboard_result['changes_today']}")

        print(f"\nNo state changes made. No email sent.")
        return

    # Send email
    if not BRIEFING_RECIPIENTS:
        logger.warning("BRIEFING_RECIPIENTS is empty — skipping email send")
        logger.info("Daily briefing complete (no email sent).")
        return

    from src.send_email import send_email

    ok = send_email(BRIEFING_RECIPIENTS, subject, email_html)
    if not ok:
        logger.error("Email delivery failed")
        sys.exit(1)

    # Log spending summary
    from src.config import SPENDING_BUDGET_USD, SPENDING_LOG_PATH
    from src.spending_guard import load_ledger, monthly_total
    ledger = load_ledger(Path(SPENDING_LOG_PATH))
    logger.info("Monthly API spend: $%.2f / $%.2f budget", monthly_total(ledger), SPENDING_BUDGET_USD)

    logger.info("Daily briefing complete.")

    # Ping Healthchecks.io dead-man-switch on successful run
    ping_url = os.environ.get("HEALTHCHECK_PING_URL")
    if ping_url:
        try:
            import requests as _req
            _req.get(ping_url, timeout=10)
        except Exception:
            pass


def _send_pushover_crash(title: str, message: str) -> None:
    """Send a Pushover alert on unhandled crash. Non-fatal."""
    try:
        import os as _os
        import requests as _req
        token = _os.environ.get("PUSHOVER_API_TOKEN", "")
        user = _os.environ.get("PUSHOVER_USER_KEY", "")
        if token and user:
            _req.post("https://api.pushover.net/1/messages.json", data={
                "token": token, "user": user,
                "title": title, "message": message[:1024], "priority": 1,
            }, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="AI Intelligence Briefing — Daily Run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pipeline without sending email or saving state")
    parser.add_argument("--layer", type=int, choices=[1, 2, 3],
                        help="Process only this layer")
    args = parser.parse_args()

    try:
        run_daily_briefing(dry_run=args.dry_run, layer=args.layer)
    except Exception as exc:
        logger.exception("Unhandled exception in AI briefing")
        _send_pushover_crash("AI Briefing CRASH", str(exc))
        sys.exit(1)
