"""Build inline-styled HTML emails for daily and quiet-day briefings."""

from __future__ import annotations

import html
import re
from datetime import datetime


def build_daily_email(
    items: list[dict],
    leaderboard: list[dict],
    backlog_summary: dict,
    dropped_counts: dict,
    total_fetched: int,
    report_date: str,
    dashboard_url: str,
) -> tuple[str, str]:
    """Build the daily briefing HTML email.

    Args:
        items: Classified items (Tier 1 and 2 only — NOTED excluded).
        leaderboard: Top 5 leaderboard entries.
        backlog_summary: Backlog stats dict.
        dropped_counts: Dict of dropped counts per layer.
        total_fetched: Total items fetched before filtering.
        report_date: Date string YYYY-MM-DD.
        dashboard_url: URL to the dashboard.

    Returns:
        Tuple of (subject_line, html_body).
    """
    long_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%B %-d, %Y")

    # Filter to only GAME_CHANGER and WORTH_YOUR_TIME for the email
    email_items = [i for i in items if i.get("tier") in ("GAME_CHANGER", "WORTH_YOUR_TIME")]

    # Sort: GAME_CHANGER first, then by layer
    tier_order = {"GAME_CHANGER": 0, "WORTH_YOUR_TIME": 1}
    email_items.sort(key=lambda x: (tier_order.get(x.get("tier"), 9), x.get("layer", 9)))

    gc_count = sum(1 for i in email_items if i.get("tier") == "GAME_CHANGER")
    total_surfaced = len(email_items)
    total_dropped = sum(dropped_counts.values())
    noted_count = len([i for i in items if i.get("tier") == "NOTED"])

    # Check for project unblocks
    has_unblock = any(i.get("unblocks_project") for i in email_items)

    # Build subject
    subject = f"AI Intel — {long_date} — {total_surfaced} items"
    if gc_count:
        subject += f" ({gc_count} game-changing)"
    if has_unblock:
        subject = f"🔓 PROJECT UNBLOCK — {subject}"

    # Build email body
    if not email_items and not leaderboard:
        body_content = _render_header(long_date) + _render_quiet_day()
    else:
        sections = [
            _render_header(long_date),
            _render_leaderboard(leaderboard),
        ]
        if email_items:
            sections.append(_render_items(email_items))
        else:
            sections.append(_render_quiet_day())

        sections.extend([
            _render_backlog_summary(backlog_summary, dashboard_url),
            _render_filter_transparency(total_fetched, total_surfaced, noted_count, total_dropped),
            _render_cta(dashboard_url),
            _render_footer(report_date),
        ])
        body_content = "".join(sections)

    html_body = _wrap_email(body_content, long_date)
    return subject, html_body


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_header(long_date: str) -> str:
    return f"""\
<tr>
  <td style="background-color:#0f172a;padding:28px 32px;">
    <p style="margin:0;color:#94a3b8;font-size:11px;letter-spacing:.1em;
              text-transform:uppercase;">AI Intelligence Briefing</p>
    <h1 style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:700;
               line-height:1.3;">Daily Briefing</h1>
    <p style="margin:4px 0 0;color:#64748b;font-size:14px;">{html.escape(long_date)}</p>
  </td>
</tr>"""


def _render_leaderboard(entries: list[dict]) -> str:
    if not entries:
        return ""

    rows = ""
    for entry in entries:
        rank = entry.get("rank", "?")
        title = html.escape(entry.get("title", ""))
        category = entry.get("category", "")
        rationale = html.escape(entry.get("rationale", ""))
        first_step = html.escape(entry.get("first_step", ""))
        time_inv = html.escape(entry.get("time_investment", ""))
        days = entry.get("days_on_leaderboard", 0)

        cat_color = _category_color(category)
        days_note = f' <span style="color:#94a3b8;font-size:11px;">({days}d)</span>' if days > 1 else ""

        rows += f"""\
<tr>
  <td style="padding:10px 16px;border-bottom:1px solid #e2e8f0;vertical-align:top;">
    <div style="display:flex;align-items:baseline;">
      <span style="font-size:20px;font-weight:700;color:#0f172a;min-width:28px;">{rank}</span>
      <div>
        <p style="margin:0;font-size:14px;font-weight:600;color:#0f172a;">
          {title}{days_note}
        </p>
        <span style="display:inline-block;font-size:10px;padding:2px 6px;border-radius:3px;
                      background-color:{cat_color};color:white;margin-top:4px;
                      text-transform:uppercase;letter-spacing:.05em;">{html.escape(category)}</span>
        <p style="margin:6px 0 0;font-size:13px;color:#475569;line-height:1.5;">{rationale}</p>
        <p style="margin:4px 0 0;font-size:12px;color:#64748b;">
          <strong>First step:</strong> {first_step} · <strong>Time:</strong> {time_inv}
        </p>
      </div>
    </div>
  </td>
</tr>"""

    return f"""\
<tr>
  <td style="padding:20px 32px 8px;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#0f172a;font-weight:700;">
      Top 5 Impact Leaderboard</h2>
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
           style="background-color:#f8fafc;border-radius:6px;border:1px solid #e2e8f0;">
      {rows}
    </table>
  </td>
</tr>"""


def _render_items(items: list[dict]) -> str:
    rows = ""
    for item in items:
        tier = item.get("tier", "")
        tier_color = "#ea580c" if tier == "GAME_CHANGER" else "#2563eb"
        tier_label = "GAME CHANGER" if tier == "GAME_CHANGER" else "WORTH YOUR TIME"

        title = html.escape(item.get("title", ""))
        source = html.escape(item.get("source_name", ""))
        why = html.escape(item.get("why_it_matters", ""))
        what = html.escape(item.get("what_it_is", ""))
        url = html.escape(item.get("url", ""))
        layer_label = {1: "Anthropic", 2: "Practitioner", 3: "Industry"}.get(item.get("layer"), "")

        # Expandable sections (always visible in email)
        expandable = ""
        impl = item.get("expandable_implement")
        if impl:
            expandable += f"""\
<div style="margin-top:10px;padding:10px 14px;background-color:#f1f5f9;
            border-left:3px solid {tier_color};border-radius:0 4px 4px 0;">
  <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#475569;
            text-transform:uppercase;letter-spacing:.05em;">Let me walk you through this</p>
  <pre style="margin:0;font-size:13px;color:#1e293b;white-space:pre-wrap;
              font-family:monospace;line-height:1.5;">{html.escape(impl)}</pre>
</div>"""

        learn = item.get("expandable_learn")
        if learn:
            expandable += f"""\
<div style="margin-top:8px;padding:10px 14px;background-color:#f0f9ff;
            border-left:3px solid #3b82f6;border-radius:0 4px 4px 0;">
  <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#475569;
            text-transform:uppercase;letter-spacing:.05em;">Here's what you need to know</p>
  <p style="margin:0;font-size:13px;color:#1e293b;line-height:1.5;">{html.escape(learn)}</p>
</div>"""

        unblock = item.get("unblocks_project")
        unblock_html = ""
        if unblock:
            unblock_html = f"""\
<div style="margin-top:8px;padding:8px 12px;background-color:#fef3c7;
            border-left:3px solid #f59e0b;border-radius:0 4px 4px 0;">
  <p style="margin:0;font-size:13px;color:#92400e;">
    🔓 <strong>Unblocks:</strong> {html.escape(unblock)}
  </p>
</div>"""

        rows += f"""\
<tr>
  <td style="padding:16px 32px;border-bottom:1px solid #e2e8f0;">
    <div>
      <span style="display:inline-block;font-size:10px;padding:3px 8px;border-radius:3px;
                    background-color:{tier_color};color:white;font-weight:700;
                    text-transform:uppercase;letter-spacing:.05em;">{tier_label}</span>
      <span style="font-size:11px;color:#94a3b8;margin-left:8px;">{source} · {layer_label}</span>
    </div>
    <h3 style="margin:8px 0 4px;font-size:16px;color:#0f172a;">
      <a href="{url}" style="color:#0f172a;text-decoration:none;">{title}</a>
    </h3>
    <p style="margin:0 0 4px;font-size:13px;color:#64748b;">{what}</p>
    <p style="margin:0;font-size:14px;color:#334155;line-height:1.6;">{why}</p>
    {unblock_html}
    {expandable}
  </td>
</tr>"""

    return f"""\
<tr>
  <td style="padding:20px 0 0;">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
      <tr><td style="padding:0 32px 8px;">
        <h2 style="margin:0;font-size:16px;color:#0f172a;font-weight:700;">Here's what caught my attention today</h2>
      </td></tr>
      {rows}
    </table>
  </td>
</tr>"""


def _render_backlog_summary(summary: dict, dashboard_url: str) -> str:
    pending = summary.get("total_pending", 0)
    if pending == 0:
        return ""

    oldest = summary.get("oldest_pending", [])
    oldest_html = ""
    if oldest and pending > 3:
        items_list = "".join(
            f'<li style="margin:2px 0;font-size:13px;color:#64748b;">'
            f'{html.escape(o["title"])} ({o["days_pending"]}d)</li>'
            for o in oldest
        )
        oldest_html = f'<ul style="margin:6px 0 0;padding-left:20px;">{items_list}</ul>'

    safe_url = html.escape(dashboard_url)
    return f"""\
<tr>
  <td style="padding:16px 32px;">
    <div style="padding:12px 16px;background-color:#f8fafc;border-radius:6px;
                border:1px solid #e2e8f0;">
      <p style="margin:0;font-size:13px;color:#475569;">
        You have <strong>{pending}</strong> pending items.
        <a href="{safe_url}" style="color:#2563eb;text-decoration:none;">View backlog →</a>
      </p>
      {oldest_html}
    </div>
  </td>
</tr>"""


def _render_filter_transparency(total_fetched: int, surfaced: int, noted: int, dropped: int) -> str:
    return f"""\
<tr>
  <td style="padding:8px 32px;">
    <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">
      I looked through {total_fetched} items today. {surfaced} were worth your time, {noted} were noted for the record, and I dropped {dropped}.
    </p>
  </td>
</tr>"""


def _render_quiet_day() -> str:
    return """\
<tr>
  <td style="padding:32px;text-align:center;">
    <p style="margin:0;font-size:16px;color:#64748b;">
      Nothing jumped out at me today — and that's a good thing.
    </p>
    <p style="margin:8px 0 0;font-size:13px;color:#94a3b8;">
      I'm still watching everything. When something matters, you'll be the first to know.
    </p>
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
      View Full Dashboard &rarr;
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap_email(body_content: str, long_date: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Intel — {html.escape(long_date)}</title>
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


def _category_color(category: str) -> str:
    colors = {
        "NEW_CAPABILITY": "#2563eb",
        "SKILL_GAP": "#7c3aed",
        "BLOCKED_PROJECT": "#dc2626",
        "STRATEGIC_MOVE": "#0d9488",
        "PARADIGM_SHIFT": "#ea580c",
        "APPLIED_PATTERN": "#ca8a04",
    }
    return colors.get(category, "#6b7280")


def _md_to_html(text: str) -> str:
    """Convert a minimal markdown subset to email-safe inline HTML."""
    escaped = html.escape(text)
    escaped = re.sub(
        r"(?m)^##\s+(.+)$",
        r'<h3 style="margin:16px 0 4px;font-size:15px;color:#0f172a;">\1</h3>',
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

    def replace_bullets(m: re.Match) -> str:
        lines = m.group(0).strip().splitlines()
        items = "".join(
            f'<li style="margin:2px 0;">{line.lstrip("- ").strip()}</li>'
            for line in lines if line.strip().startswith("- ")
        )
        return f'<ul style="margin:8px 0;padding-left:20px;">{items}</ul>'

    escaped = re.sub(r"(?m)(^- .+\n?)+", replace_bullets, escaped)

    paragraphs = re.split(r"\n{2,}", escaped.strip())
    return "".join(
        f'<p style="margin:0 0 12px;">{p.replace(chr(10), " ").strip()}</p>'
        for p in paragraphs if p.strip()
    )
