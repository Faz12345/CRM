"""SMTP email delivery for ticket receipts and account recovery messages."""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


logger = logging.getLogger(__name__)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email_address(address):
    return bool(_EMAIL_RE.fullmatch(str(address or "").strip()))


def is_configured():
    return all(
        current_app.config.get(key)
        for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM")
    )


def _send_message(message, purpose):
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(
            current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=15
        ) as smtp:
            if current_app.config["SMTP_USE_TLS"]:
                smtp.starttls(context=context)
            smtp.login(
                current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"]
            )
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("%s email delivery failed", purpose)
        return False


def send_password_reset_email(recipient, reset_token):
    """Send a one-hour password reset link over authenticated SMTP."""
    if not is_configured():
        return False

    reset_url = f"{current_app.config['APP_BASE_URL'].rstrip('/')}/reset-password?token={reset_token}"
    message = EmailMessage()
    message["Subject"] = "Reset your Support CRM password"
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        "We received a request to reset your Support CRM password.\n\n"
        f"Reset it here (the link expires in one hour):\n{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email."
    )

    return _send_message(message, "Password reset")


def send_ticket_created_email(ticket):
    """Send a ticket receipt; return sent, failed, or not_configured."""
    if not is_configured():
        return "not_configured"

    message = EmailMessage()
    message["Subject"] = f"Support request received: {ticket['ticket_id']}"
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = ticket["customer_email"]
    message.set_content(
        f"Hello {ticket['customer_name']},\n\n"
        f"We received your support request {ticket['ticket_id']} about "
        f"{ticket['subject']}.\n\n"
        "Our support team will review your request and work to resolve it as "
        "soon as possible. Keep this ticket ID for reference.\n"
    )
    return "sent" if _send_message(message, "Ticket receipt") else "failed"
