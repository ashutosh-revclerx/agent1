"""
Email Service
Email alert functionality
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple
from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
from app.services.mongodb_service import get_db
from app.core.logging import logger


def send_alert(subject: str, body: str, user_id: str = None) -> Tuple[bool, str]:
    """Send email alert to configured recipients for specific user.

    Returns:
        (True, "") on success.
        (False, reason) on failure, where reason is a human-readable description.
    """
    db = get_db()
    if db is None:
        return False, "Database unavailable — cannot read email configuration."

    # Query user-specific config if user_id provided
    query = {"user_id": user_id} if user_id else {}
    config = db.email_config.find_one(query)
    if not config:
        return False, "Email not configured. Set it up in Settings → Alerts."
    if not config.get("enabled"):
        return False, "Email alerts are disabled. Enable them in Settings → Alerts."

    recipients = config.get("recipients", [])
    if not recipients:
        return False, "No recipients configured. Add at least one email address."
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, "SMTP credentials missing in server .env (SMTP_USER / SMTP_PASSWORD)."

    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"[Email] ✅ Sent '{subject}' to {recipients}")
        return True, ""
    except Exception as e:
        logger.error(f"[Email] Error: {e}")
        return False, f"SMTP error: {e}"
