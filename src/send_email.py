"""Transactional email sending via Resend API."""

from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "IT@scmaine.com")


def send_email(
    to: list[str],
    subject: str,
    html_body: str,
) -> bool:
    """Send an HTML email via Resend.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        html_body: HTML string for the email body.

    Returns:
        True on success, False on failure (error is logged, not raised).
    """
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set — cannot send email")
        return False

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": EMAIL_FROM,
                "to": to,
                "subject": subject,
                "html": html_body,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            logger.info("Email sent to %d recipient(s): %s", len(to), subject)
            return True
        logger.error("Resend API error: %s %s", resp.status_code, resp.text)
        return False
    except Exception:
        logger.error("Failed to send email", exc_info=True)
        return False
