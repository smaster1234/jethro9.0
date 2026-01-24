"""
Email Utilities
===============

Email sending functionality for password reset and notifications.
Supports both SMTP and mock mode for development.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)


def get_email_config():
    """Get email configuration from environment variables."""
    return {
        "smtp_host": os.environ.get("SMTP_HOST", ""),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
        "smtp_from": os.environ.get("SMTP_FROM", "noreply@jethro.legal"),
        "smtp_use_tls": os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
        "app_url": os.environ.get("APP_URL", "http://localhost:5173"),
    }


def is_email_configured() -> bool:
    """Check if SMTP is properly configured."""
    config = get_email_config()
    return bool(config["smtp_host"] and config["smtp_user"] and config["smtp_password"])


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None
) -> bool:
    """
    Send an email.

    Returns True if sent successfully, False otherwise.
    In development mode (SMTP not configured), logs the email instead.
    """
    config = get_email_config()

    if not is_email_configured():
        logger.info(f"[DEV MODE] Email would be sent to {to_email}: {subject}")
        logger.debug(f"[DEV MODE] Email body: {text_body or html_body[:200]}")
        return True  # Return True in dev mode to not block flow

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config["smtp_from"]
        msg["To"] = to_email

        # Add text version
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))

        # Add HTML version
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # Connect and send
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            if config["smtp_use_tls"]:
                server.starttls()
            server.login(config["smtp_user"], config["smtp_password"])
            server.sendmail(config["smtp_from"], to_email, msg.as_string())

        logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_password_reset_email(to_email: str, reset_token: str, user_name: Optional[str] = None) -> bool:
    """
    Send a password reset email.

    Args:
        to_email: Recipient email address
        reset_token: The password reset token
        user_name: Optional user name for personalization

    Returns:
        True if sent successfully, False otherwise
    """
    config = get_email_config()
    app_url = config["app_url"].rstrip("/")
    reset_link = f"{app_url}/reset-password?token={reset_token}"

    greeting = f"שלום {user_name}," if user_name else "שלום,"

    html_body = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="he">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; direction: rtl; text-align: right; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: white; margin: 0; font-size: 24px; }}
            .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0; }}
            .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            .warning {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Jethro Legal</h1>
            </div>
            <div class="content">
                <p>{greeting}</p>
                <p>קיבלנו בקשה לאיפוס הסיסמה שלך במערכת Jethro Legal.</p>
                <p>לחץ על הכפתור הבא כדי לאפס את הסיסמה:</p>

                <center>
                    <a href="{reset_link}" class="button">איפוס סיסמה</a>
                </center>

                <div class="warning">
                    <strong>שים לב:</strong> קישור זה תקף לשעה אחת בלבד.
                    אם לא ביקשת לאפס את הסיסמה, התעלם מהודעה זו.
                </div>

                <p>אם הכפתור לא עובד, העתק את הקישור הבא לדפדפן:</p>
                <p style="word-break: break-all; background: #e9ecef; padding: 10px; border-radius: 5px; font-size: 12px;">
                    {reset_link}
                </p>
            </div>
            <div class="footer">
                <p>הודעה זו נשלחה אוטומטית ממערכת Jethro Legal</p>
                <p>אין להשיב להודעה זו</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
{greeting}

קיבלנו בקשה לאיפוס הסיסמה שלך במערכת Jethro Legal.

לאיפוס הסיסמה, היכנס לקישור הבא:
{reset_link}

שים לב: קישור זה תקף לשעה אחת בלבד.
אם לא ביקשת לאפס את הסיסמה, התעלם מהודעה זו.

בברכה,
צוות Jethro Legal
"""

    return send_email(
        to_email=to_email,
        subject="איפוס סיסמה - Jethro Legal",
        html_body=html_body,
        text_body=text_body
    )
