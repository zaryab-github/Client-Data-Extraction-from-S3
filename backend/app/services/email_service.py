"""Email delivery (Phase 8).

Sends a completed report by email. Small reports are attached as a ZIP; large
reports (over EMAIL_MAX_ATTACHMENT_BYTES) are sent as a short-lived secure download
link (reusing the signed download-token mechanism).

Primary provider is **Gmail via OAuth2** (refresh token → access token → Gmail API).
SMTP is also supported. All config comes from .env.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_download_token
from app.db.models.email_delivery import EmailDelivery, EmailMethod, EmailStatus
from app.db.models.job import ExtractionJob, ReportMetadata

logger = logging.getLogger(__name__)

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class EmailError(Exception):
    pass


# ── Gmail OAuth2 ───────────────────────────────────────────
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _gmail_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] - 60 > now:
        return _token_cache["access_token"]
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        if not getattr(settings, name):
            raise EmailError(f"{name} is not configured.")
    data = urllib.parse.urlencode(
        {
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "refresh_token": settings.GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(settings.GMAIL_TOKEN_URI, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # noqa: UP041
        raise EmailError(f"Gmail token exchange failed: {exc.read().decode(errors='replace')}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EmailError(f"Gmail token exchange failed: {exc}") from exc
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
    return _token_cache["access_token"]


def _gmail_send(msg: EmailMessage) -> str:
    token = _gmail_access_token()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = json.dumps({"raw": raw}).encode()
    req = urllib.request.Request(
        GMAIL_SEND_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # noqa: UP041
        raise EmailError(f"Gmail send failed: {exc.read().decode(errors='replace')}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EmailError(f"Gmail send failed: {exc}") from exc
    return result.get("id", "")


# ── SMTP (fallback provider) ───────────────────────────────
def _smtp_send(msg: EmailMessage) -> str:
    import smtplib

    if not settings.SMTP_HOST:
        raise EmailError("SMTP_HOST is not configured.")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)
    return ""


def _sender_address() -> str:
    if settings.EMAIL_PROVIDER == "gmail":
        return settings.GMAIL_SENDER or settings.EMAIL_FROM_ADDRESS
    return settings.EMAIL_FROM_ADDRESS or settings.GMAIL_SENDER


def _build_message(
    to: str, subject: str, text: str, html: str,
    attachment: bytes | None = None, attachment_name: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = _sender_address()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    if attachment is not None:
        msg.add_attachment(
            attachment, maintype="application", subtype="zip",
            filename=attachment_name or "report.zip",
        )
    return msg


def _send_via_provider(msg: EmailMessage) -> str:
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "gmail":
        return _gmail_send(msg)
    if provider == "smtp":
        return _smtp_send(msg)
    raise EmailError(f"Unsupported EMAIL_PROVIDER: {settings.EMAIL_PROVIDER}")


def _download_link(job_id: str, owner_id) -> str:
    token = create_download_token(str(owner_id), job_id)
    base = settings.PUBLIC_API_BASE_URL.rstrip("/")
    if not base:
        raise EmailError("PUBLIC_API_BASE_URL is not configured (needed for email links).")
    return f"{base}/reports/{job_id}/download?token={urllib.parse.quote(token)}"


# ── Orchestration ──────────────────────────────────────────
def send_report_email(db: Session, delivery: EmailDelivery) -> EmailDelivery:
    """Build and send the report email for a delivery; update its status."""
    if not settings.EMAIL_ENABLED:
        delivery.status = EmailStatus.FAILED
        delivery.error = "Email is disabled (EMAIL_ENABLED=false)."
        db.commit()
        return delivery

    job = db.scalar(select(ExtractionJob).where(ExtractionJob.job_id == delivery.job_id))
    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == delivery.job_id))
    if job is None or report is None:
        delivery.status = EmailStatus.FAILED
        delivery.error = "Job or report not found."
        db.commit()
        return delivery

    codes = ", ".join(job.requested_shortcodes) if job.requested_shortcodes else "—"
    rng = f"{job.date_from:%Y-%m-%d %H:%M} → {job.date_to:%Y-%m-%d %H:%M}"
    subject = f"Extraction report {job.job_id} ({codes})"

    use_attachment = report.zip_size_bytes <= settings.EMAIL_MAX_ATTACHMENT_BYTES
    delivery.method = EmailMethod.ATTACHMENT if use_attachment else EmailMethod.LINK

    lines_common = (
        f"Job: {job.job_id}\n"
        f"Shortcodes: {codes}\n"
        f"Range: {rng}\n"
        f"Records: {report.csv_row_count:,}\n"
        f"ZIP size: {report.zip_size_bytes / 1048576:.2f} MB\n"
    )

    try:
        if use_attachment:
            with open(report.zip_path, "rb") as f:
                data = f.read()
            text = f"Your extraction report is attached.\n\n{lines_common}"
            html = (
                f"<p>Your extraction report is attached.</p>"
                f"<pre>{lines_common}</pre>"
            )
            msg = _build_message(
                delivery.recipient, subject, text, html,
                attachment=data, attachment_name=report.zip_filename,
            )
        else:
            link = _download_link(job.job_id, job.user_id)
            mins = settings.DOWNLOAD_LINK_EXPIRE_MINUTES
            text = (
                f"Your extraction report is ready. Download it here (link valid for "
                f"{mins} minutes):\n{link}\n\n{lines_common}"
            )
            html = (
                f"<p>Your extraction report is ready.</p>"
                f'<p><a href="{link}">Download report</a> '
                f"(link valid for {mins} minutes)</p><pre>{lines_common}</pre>"
            )
            msg = _build_message(delivery.recipient, subject, text, html)

        message_id = _send_via_provider(msg)
        delivery.status = EmailStatus.SENT
        delivery.provider_message_id = message_id or None
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.error = None
        logger.info("Email SENT for %s to %s", delivery.job_id, delivery.recipient)
    except Exception as exc:  # noqa: BLE001
        delivery.status = EmailStatus.FAILED
        delivery.error = f"{type(exc).__name__}: {exc}"
        logger.exception("Email FAILED for %s", delivery.job_id)

    db.commit()
    return delivery
