"""Gmail API authentication and email sending (send-only, no fetching)."""

from __future__ import annotations

import base64
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource

load_dotenv()

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


def authenticate() -> Resource:
    """Authenticate with Gmail API and return a service object.

    Loads saved credentials from token file if available. Refreshes expired
    credentials automatically. Runs the OAuth browser flow for first-time auth
    and saves the resulting token for future use.

    Returns:
        Authenticated Gmail API service (googleapiclient Resource).
    """
    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "token.json")

    creds: Credentials | None = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        logger.debug("Loaded credentials from %s", token_path)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail credentials")
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth flow — browser will open")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        os.chmod(token_path, 0o600)
        logger.info("Saved credentials to %s", token_path)

    service = build("gmail", "v1", credentials=creds)
    logger.info("Gmail API authenticated successfully")
    return service


def send_email(
    service: Resource,
    to: list[str],
    subject: str,
    html_body: str,
) -> bool:
    """Send an HTML email from the authenticated Gmail account.

    Args:
        service: Authenticated Gmail API service resource.
        to: List of recipient email addresses.
        subject: Email subject line.
        html_body: HTML string for the email body.

    Returns:
        True on success, False on failure (error is logged, not raised).
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = "me"
        msg["To"] = ", ".join(to)
        msg.attach(MIMEText(html_body, "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info("Email sent to %d recipient(s): %s", len(to), subject)
        return True
    except Exception:
        logger.error("Failed to send email", exc_info=True)
        return False
