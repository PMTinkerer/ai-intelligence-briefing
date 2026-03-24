"""Build the weekly rollup HTML email (Saturday mornings)."""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

from src.config import SPENDING_BUDGET_USD, SPENDING_LOG_PATH, SPENDING_WARN_THRESHOLD
from src.spending_guard import can_spend, load_ledger, record_spend, save_ledger
from src.state import load_json_or_default

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5-20250929"


def build_weekly_email(
    briefings_path: Path,
    backlog_path: Path,
    blocked_projects_path: Path,
    api_key: str,
    report_date: str,
    dashboard_url: str,
) -> tuple[str, str]:
    """Build the weekly rollup email.

    Args:
        briefings_path: Path to briefings.json.
        backlog_path: Path to backlog.json.
        blocked_projects_path: Path to blocked_projects.json.
        api_key: Anthropic API key.
        report_date: Saturday date YYYY-MM-DD.
        dashboard_url: URL to the dashboard.

    Returns:
        Tuple of (subject_line, html_body).
    """
    long_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%B %-d, %Y")

    # Load data
    briefings = load_json_or_default(briefings_path, [])
    backlog_data = load_json_or_default(backlog_path, {"items": [], "stats": {}})
    blocked_data = load_json_or_default(blocked_projects_path, {"blocked_projects": []})

    # Filter briefings to last 7 days
    cutoff = (datetime.strptime(report_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    week_briefings = [b for b in briefings if b.get("date", "") >= cutoff]

    # Gather week's items
    week_items = []
    for b in week_briefings:
        week_items.extend(b.get("items", []))

    # Backlog stats
    backlog_items = backlog_data.get("items", [])
    adopted_this_week = [
        i for i in backlog_items
        if i.get("status") == "adopted" and (i.get("date_adopted") or "") >= cutoff
    ]
    archived_this_week = [
        i for i in backlog_items
        if i.get("status") == "archived" and (i.get("date_archived") or "") >= cutoff
    ]
    pending = [i for i in backlog_items if i.get("status") == "pending"]
    stats = backlog_data.get("stats", {})

    # Generate AI synthesis
    synthesis = _generate_synthesis(week_items, api_key)

    # Subject
    subject = (f"AI Intel Weekly — Week of {long_date} — "
               f"{len(adopted_this_week)} adopted, {len(pending)} pending")

    # Build HTML
    sections = [
        _render_header(long_date),
        _render_synthesis(synthesis),
        _render_adoption_report(adopted_this_week, archived_this_week, pending, stats),
        _render_blocked_projects(blocked_data.get("blocked_projects", []), week_items),
        _render_cta(dashboard_url),
        _render_footer(report_date),
    ]

    body_content = "".join(sections)
    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Intel Weekly — {html.escape(long_date)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
       style="background-color:#f1f5f9;">
  <tr>
    <td align="center" style="padding:24px 16px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="max-width:600px;background-color:#ffffff;border-radius:8px;
                    overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1);">
        {body_content}
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

    return subject, html_body


def _generate_synthesis(week_items: list[dict], api_key: str) -> str:
    """Generate a 3-5 sentence week-in-review synthesis via API.

    Args:
        week_items: All classified items from the past week.
        api_key: Anthropic API key.

    Returns:
        Synthesis text, or a fallback message on failure.
    """
    if not week_items or not api_key:
        return "Quiet week — no significant items surfaced."

    ledger = load_ledger(Path(SPENDING_LOG_PATH))
    if not can_spend(ledger, SPENDING_BUDGET_USD, estimated_cost=0.05,
                     warn_threshold=SPENDING_WARN_THRESHOLD):
        return "Weekly synthesis skipped (budget limit reached)."

    titles = [f"- [{i.get('tier', '?')}] {i.get('title', '?')}" for i in week_items[:20]]
    items_text = "\n".join(titles)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system="You write concise weekly summaries of AI developments for a business operator. "
                   "Synthesize the week's themes in 3-5 sentences. Focus on what matters most and "
                   "what the operator should prioritize if they only have 10 minutes this week.",
            messages=[{"role": "user", "content": f"This week's items:\n\n{items_text}"}],
        )

        usage = response.usage
        cost = record_spend(ledger, "anthropic", _MODEL,
                            usage.input_tokens, usage.output_tokens, "weekly_synthesis")
        save_ledger(ledger, Path(SPENDING_LOG_PATH))
        logger.info("Weekly synthesis: $%.4f", cost)

        return response.content[0].text.strip()

    except Exception:
        logger.warning("Weekly synthesis failed", exc_info=True)
        return "Weekly synthesis could not be generated."


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_header(long_date: str) -> str:
    return f"""\
<tr>
  <td style="background-color:#0f172a;padding:28px 32px;">
    <p style="margin:0;color:#94a3b8;font-size:11px;letter-spacing:.1em;
              text-transform:uppercase;">AI Intelligence Briefing</p>
    <h1 style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:700;">
      Weekly Rollup</h1>
    <p style="margin:4px 0 0;color:#64748b;font-size:14px;">
      Week of {html.escape(long_date)}</p>
  </td>
</tr>"""


def _render_synthesis(synthesis: str) -> str:
    return f"""\
<tr>
  <td style="padding:24px 32px;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#0f172a;">Week in Review</h2>
    <p style="margin:0;font-size:14px;color:#334155;line-height:1.7;">
      {html.escape(synthesis)}</p>
  </td>
</tr>"""


def _render_adoption_report(adopted: list, archived: list, pending: list, stats: dict) -> str:
    adopted_html = ""
    if adopted:
        items = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:#15803d;">'
            f'✓ {html.escape(i.get("title", ""))} (adopted {i.get("date_adopted", "")})</li>'
            for i in adopted
        )
        adopted_html = f'<ul style="margin:8px 0;padding-left:20px;">{items}</ul>'

    archived_html = ""
    if archived:
        items = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:#94a3b8;">'
            f'{html.escape(i.get("title", ""))} (auto-archived after 21d)</li>'
            for i in archived
        )
        archived_html = f'<ul style="margin:8px 0;padding-left:20px;">{items}</ul>'

    rate = stats.get("adoption_rate_4w", 0)

    return f"""\
<tr>
  <td style="padding:16px 32px;border-top:1px solid #e2e8f0;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#0f172a;">Adoption Report</h2>
    <p style="margin:0;font-size:14px;color:#334155;">
      <strong>{len(adopted)}</strong> adopted this week ·
      <strong>{len(archived)}</strong> auto-archived ·
      <strong>{len(pending)}</strong> still pending ·
      4-week adoption rate: <strong>{rate:.0%}</strong>
    </p>
    {adopted_html}
    {archived_html}
  </td>
</tr>"""


def _render_blocked_projects(projects: list[dict], week_items: list[dict]) -> str:
    if not projects:
        return ""

    rows = ""
    for proj in projects:
        name = html.escape(proj.get("project", ""))
        status = html.escape(proj.get("status", ""))
        blocker = html.escape(proj.get("blocker", ""))

        # Check if any item this week mentions an unblock
        unblocked = any(
            i.get("unblocks_project") and proj["project"].lower() in i["unblocks_project"].lower()
            for i in week_items
        )
        status_color = "#15803d" if unblocked else "#64748b"
        status_text = "Movement this week!" if unblocked else "No change"

        rows += f"""\
<tr>
  <td style="padding:8px 0;border-bottom:1px solid #f1f5f9;">
    <p style="margin:0;font-size:14px;font-weight:600;color:#0f172a;">{name}</p>
    <p style="margin:2px 0;font-size:13px;color:#64748b;">{blocker}</p>
    <p style="margin:2px 0;font-size:12px;color:{status_color};font-weight:600;">{status_text}</p>
  </td>
</tr>"""

    return f"""\
<tr>
  <td style="padding:16px 32px;border-top:1px solid #e2e8f0;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#0f172a;">Blocked Projects</h2>
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
      {rows}
    </table>
  </td>
</tr>"""


def _render_cta(dashboard_url: str) -> str:
    safe_url = html.escape(dashboard_url)
    return f"""\
<tr>
  <td align="center" style="padding:20px 32px 24px;">
    <a href="{safe_url}"
       style="display:inline-block;background-color:#0f172a;color:#ffffff;
              font-size:14px;font-weight:700;text-decoration:none;
              padding:12px 28px;border-radius:6px;">
      View Dashboard &rarr;
    </a>
  </td>
</tr>"""


def _render_footer(report_date: str) -> str:
    return f"""\
<tr>
  <td style="background-color:#f8fafc;padding:14px 32px;
             border-top:1px solid #e2e8f0;">
    <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">
      Generated by AI Intelligence Briefing · {html.escape(report_date)}
    </p>
  </td>
</tr>"""
