"""Weekly rollup orchestrator (Saturday mornings)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path("config")
_DATA_DIR = Path("data")


def run_weekly_rollup(dry_run: bool = False) -> None:
    """Run the weekly rollup pipeline.

    Args:
        dry_run: If True, print output without sending email.
    """
    from src.config import ANTHROPIC_API_KEY, BRIEFING_RECIPIENTS, DASHBOARD_URL
    from src.generate_weekly import build_weekly_email

    report_date = date.today().isoformat()
    logger.info("Starting weekly rollup for %s (dry_run=%s)", report_date, dry_run)

    briefings_path = _DATA_DIR / "briefings.json"
    backlog_path = _DATA_DIR / "backlog.json"
    blocked_path = _CONFIG_DIR / "blocked_projects.json"

    subject, email_html = build_weekly_email(
        briefings_path=briefings_path,
        backlog_path=backlog_path,
        blocked_projects_path=blocked_path,
        api_key=ANTHROPIC_API_KEY,
        report_date=report_date,
        dashboard_url=DASHBOARD_URL,
    )

    if dry_run:
        print(f"\n{'='*60}")
        print(f"WEEKLY ROLLUP DRY RUN — {report_date}")
        print(f"{'='*60}")
        print(f"Subject: {subject}")
        print(f"Email HTML: {len(email_html)} bytes")
        print(f"\nNo email sent.")
        return

    if not BRIEFING_RECIPIENTS:
        logger.warning("BRIEFING_RECIPIENTS is empty — skipping email send")
        logger.info("Weekly rollup complete (no email sent).")
        return

    from src.send_email import send_email

    ok = send_email(BRIEFING_RECIPIENTS, subject, email_html)
    if not ok:
        logger.error("Weekly email delivery failed")
        sys.exit(1)

    logger.info("Weekly rollup complete.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="AI Intelligence Briefing — Weekly Rollup")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without sending email")
    args = parser.parse_args()

    run_weekly_rollup(dry_run=args.dry_run)
