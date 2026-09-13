"""Transactional email via the SendByte API (https://sendbyte.africa).

SendByte contract: ``POST {base}/emails`` with JSON ``{from, to, subject, html}``
and ``Authorization: Bearer <api key>``. Keys look like ``sk_test_...`` (sandbox)
or ``sk_live_...`` (production).

Email sending is best-effort: callers hand this module to BackgroundTasks, and
failures are logged and reported to Sentry rather than raised, so a SendByte
outage never fails the request that triggered the mail.
"""

from __future__ import annotations

import html as html_escape_module
import logging
import os

import httpx
import sentry_sdk

logger = logging.getLogger("aura.email")

SENDBYTE_API_KEY = os.getenv("SENDBYTE_API_KEY", "")
SENDBYTE_FROM_EMAIL = os.getenv("SENDBYTE_FROM_EMAIL", "")
SENDBYTE_BASE_URL = os.getenv("SENDBYTE_BASE_URL", "https://api.sendbyte.africa/v1")

_BRAND_COLOR = "#5b5bf6"


def email_configured() -> bool:
    """True when both an API key and a from-address are set."""
    return bool(SENDBYTE_API_KEY and SENDBYTE_FROM_EMAIL)


def get_public_api_url(frontend_url: str, environment: str) -> str:
    """Public base URL where a browser can reach the backend API.

    Email links must be clickable from outside the docker network. The nginx
    frontend proxies ``/api/<path>`` to the backend's ``/<path>``, so in
    production the backend is reachable at ``{FRONTEND_URL}/api``. Override
    with ``PUBLIC_API_URL`` for non-standard proxy layouts.
    """
    explicit = os.getenv("PUBLIC_API_URL", "")
    if explicit:
        return explicit.rstrip("/")
    if environment == "production":
        return frontend_url.rstrip("/") + "/api"
    return "http://localhost:8000"


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send one email through SendByte. Returns True on accepted send.

    Never raises: a failure is logged (with the provider's response when
    available) and captured in Sentry, then reported as False. When the
    integration is unconfigured (no API key), logs a warning and returns
    False so local development works without SendByte credentials.
    """
    if not email_configured():
        logger.warning(
            "SENDBYTE_API_KEY/SENDBYTE_FROM_EMAIL not configured; skipping email to %s",
            to,
        )
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{SENDBYTE_BASE_URL}/emails",
                json={
                    "from": SENDBYTE_FROM_EMAIL,
                    "to": to,
                    "subject": subject,
                    "html": html,
                },
                headers={"Authorization": f"Bearer {SENDBYTE_API_KEY}"},
            )
            if resp.status_code >= 400:
                logger.error(
                    "SendByte send failed (%s): %s", resp.status_code, resp.text[:500]
                )
                sentry_sdk.capture_message(
                    f"SendByte email send failed: {resp.status_code}"
                )
                return False
            return True
    except Exception as e:
        logger.error("SendByte email error: %s", e, exc_info=True)
        sentry_sdk.capture_exception(e)
        return False


def _base_html(preheader: str, body: str, cta_href: str, cta_text: str, footnote: str) -> str:
    esc = html_escape_module.escape
    return f"""\
<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background-color:#ffffff;border-radius:12px;padding:40px;border:1px solid #e5e7eb;">
        <tr><td style="font-size:20px;font-weight:700;color:#111827;padding-bottom:4px;">Aura</td></tr>
        <tr><td style="font-size:14px;color:#6b7280;padding-bottom:24px;">AI Interviewer</td></tr>
        <tr><td style="font-size:22px;font-weight:700;color:#111827;padding-bottom:12px;">{esc(preheader)}</td></tr>
        <tr><td style="font-size:15px;line-height:1.6;color:#374151;padding-bottom:28px;">{body}</td></tr>
        <tr><td align="center" style="padding-bottom:28px;">{f'<a href="{cta_href}" style="display:inline-block;background-color:{_BRAND_COLOR};color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:12px 32px;border-radius:8px;">{esc(cta_text)}</a>' if cta_text else ''}</td></tr>
        <tr><td style="font-size:13px;line-height:1.5;color:#9ca3af;padding-bottom:8px;">{footnote}</td></tr>
        <tr><td style="font-size:12px;color:#d1d5db;border-top:1px solid #f3f4f6;padding-top:16px;">You are receiving this email because an Aura account was created with this address. If this wasn't you, you can safely ignore it.</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def verification_email_html(name: str, verify_url: str) -> str:
    first = name.split()[0] if name and name.split() else "there"
    return _base_html(
        preheader="Confirm your email address",
        body=(f"Hi {html_escape_module.escape(first)},<br/><br/>"
              "Welcome to Aura! Please confirm your email address to activate your "
              "account and start your AI-powered voice interviews."),
        cta_href=verify_url,
        cta_text="Verify my email",
        footnote=(f"This link expires in 24 hours. If the button doesn't work, copy this URL into your "
                  f"browser:<br/>{html_escape_module.escape(verify_url)}"),
    )


def welcome_email_html(name: str, frontend_url: str) -> str:
    first = name.split()[0] if name and name.split() else "there"
    return _base_html(
        preheader="Welcome to Aura",
        body=(f"Hi {html_escape_module.escape(first)},<br/><br/>"
              "Your Aura account is ready. Upload a resume and practice a real-time "
              "voice interview — Aura will ask personalized questions, probe deeper on "
              "your answers, and give you a structured report at the end."),
        cta_href=frontend_url.rstrip("/"),
        cta_text="Start your first interview",
        footnote="You can sign in anytime with Google or GitHub — no password needed.",
    )


def password_reset_email_html(name: str, reset_url: str) -> str:
    first = name.split()[0] if name and name.split() else "there"
    return _base_html(
        preheader="Reset your password",
        body=(f"Hi {html_escape_module.escape(first)},<br/><br/>"
              "We received a request to reset your Aura password. Click the button "
              "below to choose a new one."),
        cta_href=reset_url,
        cta_text="Reset password",
        footnote=("This link expires in 1 hour and can only be used once. If you didn't request a "
                  "reset, you can safely ignore this email — your password is unchanged."),
    )
