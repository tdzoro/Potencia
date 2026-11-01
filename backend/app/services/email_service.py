"""Email delivery service with SMTP integration and responsive HTML templates.

Supports:
- Outbound SMTP delivery over TLS/SSL with authentication.
- Hermetic development and test mode when `SMTP_HOST` is unset, recording sent
  messages in `sent_emails` for automated assertions without external network dependencies.
- Dual-content MIME formatting (Plain text + responsive HTML).
- Anti-leak safety: raw tokens and credentials are never logged.
"""

from __future__ import annotations

import html
import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentEmail:
    to_email: str
    subject: str
    plain_content: str
    html_content: str


# In-memory queue used during tests and local development when no SMTP host is configured
_SENT_EMAILS: list[SentEmail] = []


def get_sent_emails() -> list[SentEmail]:
    """Retrieve sent emails recorded in dev/test mode."""
    return list(_SENT_EMAILS)


def clear_sent_emails() -> None:
    """Clear the in-memory email log (useful between test runs)."""
    _SENT_EMAILS.clear()


def _render_email_layout(
    *,
    preheader: str,
    title: str,
    content_html: str,
    action_url: str | None = None,
    action_label: str | None = None,
    expiry_notice: str | None = None,
) -> str:
    """Render a responsive, dark-mode compatible branded HTML email template."""
    action_button_html = ""
    if action_url and action_label:
        action_button_html = f"""
        <table border="0" cellpadding="0" cellspacing="0" style="margin: 28px 0;">
            <tr>
                <td align="center" style="border-radius: 10px; background-color: #6D3BF5;">
                    <a href="{html.escape(action_url)}" target="_blank" style="display: inline-block; padding: 14px 28px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: 600; color: #FFFFFF; text-decoration: none; border-radius: 10px; letter-spacing: 0.02em;">
                        {html.escape(action_label)} &rarr;
                    </a>
                </td>
            </tr>
        </table>
        <p style="margin: 0 0 16px 0; font-size: 12px; line-height: 1.5; color: #8C8FA1;">
            If the button doesn't work, copy and paste this URL into your browser:<br/>
            <a href="{html.escape(action_url)}" style="color: #A78BFA; word-break: break-all;">{html.escape(action_url)}</a>
        </p>
        """

    expiry_html = ""
    if expiry_notice:
        expiry_html = f"""
        <p style="margin: 16px 0 0 0; font-size: 12px; color: #F59E0B; line-height: 1.5;">
            &#9202; {html.escape(expiry_notice)}
        </p>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <!--[if mso]>
    <style type="text/css">
        table {{border-collapse:collapse;border-spacing:0;margin:0;}}
        div, td {{padding:0;}}
        div {{margin:0 !important;}}
    </style>
    <![endif]-->
</head>
<body style="margin:0; padding:0; background-color: #0B0C10; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #E2E8F0;">
    <div style="display:none; font-size:1px; color:#0B0C10; line-height:1px; max-height:0px; max-width:0px; opacity:0; overflow:hidden;">
        {html.escape(preheader)}
    </div>
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0B0C10; padding: 40px 16px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 540px; background-color: #12141A; border: 1px solid #232634; border-radius: 16px; padding: 36px 32px; box-shadow: 0 8px 32px rgba(0,0,0,0.4);">
                    <tr>
                        <td align="left" style="padding-bottom: 24px; border-bottom: 1px solid #1E212D;">
                            <span style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 20px; font-weight: 800; letter-spacing: 0.08em; color: #FFFFFF;">
                                POTENCIA<span style="color: #6D3BF5;">.</span>
                            </span>
                            <span style="display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.15em; color: #8C8FA1; margin-top: 4px;">
                                AI Resume Intelligence
                            </span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-top: 28px;">
                            <h1 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700; color: #FFFFFF; letter-spacing: -0.01em;">
                                {html.escape(title)}
                            </h1>
                            <div style="font-size: 14px; line-height: 1.6; color: #CBD5E1;">
                                {content_html}
                            </div>
                            {action_button_html}
                            {expiry_html}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding-top: 32px; border-top: 1px solid #1E212D; margin-top: 32px;">
                            <p style="margin: 0; font-size: 11px; line-height: 1.5; color: #64748B;">
                                This security notification was sent automatically by POTENCIA. If you did not initiate this request, no action is needed — your account remains protected.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def _send_email(to_email: str, subject: str, plain_content: str, html_content: str) -> None:
    """Dispatch an email via SMTP or record to in-memory queue."""
    settings = get_settings()

    # If SMTP is not configured, operate in hermetic test/development mode
    if not settings.smtp_host:
        logger.info("Recorded dev/test email to %s: '%s'", to_email, subject)
        _SENT_EMAILS.append(
            SentEmail(
                to_email=to_email,
                subject=subject,
                plain_content=plain_content,
                html_content=html_content,
            )
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(plain_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if settings.smtp_port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)

        with server:
            if settings.smtp_use_tls and settings.smtp_port != 465:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        logger.info("Successfully delivered email to %s: '%s'", to_email, subject)
    except Exception as exc:
        # Catch and log without exposing credentials or internal tokens
        logger.error("Failed to deliver email via SMTP to %s: %s", to_email, type(exc).__name__)


def send_verification_email(to_email: str, name: str | None, raw_token: str) -> None:
    """Dispatch an email verification link to a registered account."""
    settings = get_settings()
    frontend_url = settings.frontend_url.rstrip("/")
    verify_url = f"{frontend_url}/verify-email?token={raw_token}"
    greeting = f"Hi {name}," if name else "Hello,"

    subject = "Verify your POTENCIA account"
    preheader = "Confirm your email address to activate your POTENCIA account."

    content_html = f"""
    <p style="margin: 0 0 12px 0;">{html.escape(greeting)}</p>
    <p style="margin: 0 0 12px 0;">
        Thank you for joining POTENCIA. Please confirm your email address to verify your account
        and activate full access to deterministic resume scoring, ATS analysis, and the improvement studio.
    </p>
    """

    plain_content = f"""{greeting}

Thank you for joining POTENCIA. Please confirm your email address to activate your account:

{verify_url}

This verification link expires in {settings.verification_token_expire_hours} hours.

If you did not create an account on POTENCIA, you can safely ignore this email.
"""

    html_content = _render_email_layout(
        preheader=preheader,
        title="Verify your email address",
        content_html=content_html,
        action_url=verify_url,
        action_label="Verify Email Address",
        expiry_notice=f"This verification link expires in {settings.verification_token_expire_hours} hours.",
    )

    _send_email(to_email, subject, plain_content, html_content)


def send_password_reset_email(to_email: str, name: str | None, raw_token: str) -> None:
    """Dispatch a secure password recovery link to the user."""
    settings = get_settings()
    frontend_url = settings.frontend_url.rstrip("/")
    reset_url = f"{frontend_url}/reset-password?token={raw_token}"
    greeting = f"Hi {name}," if name else "Hello,"

    subject = "Reset your POTENCIA password"
    preheader = "A password reset request was received for your POTENCIA account."

    content_html = f"""
    <p style="margin: 0 0 12px 0;">{html.escape(greeting)}</p>
    <p style="margin: 0 0 12px 0;">
        We received a request to reset the password for your POTENCIA account.
        Click the button below to choose a new, secure password.
    </p>
    """

    plain_content = f"""{greeting}

We received a request to reset the password for your POTENCIA account.

Click the link below to set a new password:
{reset_url}

This password reset link expires in {settings.password_reset_token_expire_minutes} minutes and can only be used once.

If you did not request a password reset, please ignore this email. Your password will remain unchanged.
"""

    html_content = _render_email_layout(
        preheader=preheader,
        title="Password Reset Request",
        content_html=content_html,
        action_url=reset_url,
        action_label="Reset Password",
        expiry_notice=f"This one-time link expires in {settings.password_reset_token_expire_minutes} minutes.",
    )

    _send_email(to_email, subject, plain_content, html_content)


def send_password_changed_notification(to_email: str, name: str | None) -> None:
    """Notify the user that their password was successfully updated."""
    greeting = f"Hi {name}," if name else "Hello,"
    subject = "Your POTENCIA password was changed"
    preheader = "Your account password has been updated."

    content_html = f"""
    <p style="margin: 0 0 12px 0;">{html.escape(greeting)}</p>
    <p style="margin: 0 0 12px 0;">
        This email confirms that the password for your POTENCIA account was recently changed.
        All previous active sessions have been signed out for your security.
    </p>
    <p style="margin: 0 0 12px 0; color: #F87171;">
        If you did not perform this change, please contact your administrator or reset your password immediately.
    </p>
    """

    plain_content = f"""{greeting}

This email confirms that the password for your POTENCIA account was recently changed.
All previous active sessions have been signed out for your security.

If you did not perform this change, please reset your password immediately.
"""

    html_content = _render_email_layout(
        preheader=preheader,
        title="Password Changed",
        content_html=content_html,
    )

    _send_email(to_email, subject, plain_content, html_content)


def send_welcome_email(to_email: str, name: str | None) -> None:
    """Send a welcome confirmation email once the account is verified."""
    settings = get_settings()
    frontend_url = settings.frontend_url.rstrip("/")
    login_url = f"{frontend_url}/login"
    greeting = f"Hi {name}," if name else "Hello,"
    subject = "Welcome to POTENCIA"
    preheader = "Your POTENCIA account has been verified."

    content_html = f"""
    <p style="margin: 0 0 12px 0;">{html.escape(greeting)}</p>
    <p style="margin: 0 0 12px 0;">
        Your email has been verified and your account is fully activated.
        You can now upload resumes, generate explainable ATS scores, and access the improvement studio.
    </p>
    """

    plain_content = f"""{greeting}

Your email has been verified and your account is fully activated.
You can now sign in and upload resumes at {login_url}
"""

    html_content = _render_email_layout(
        preheader=preheader,
        title="Account Activated",
        content_html=content_html,
        action_url=login_url,
        action_label="Go to Dashboard",
    )

    _send_email(to_email, subject, plain_content, html_content)

