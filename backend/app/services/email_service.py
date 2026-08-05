"""Email delivery (Phase 8).

Sends a completed report by email. Small reports are attached as a ZIP; large reports
(over EMAIL_MAX_ATTACHMENT_BYTES) are uploaded to **Google Drive**, shared as
"anyone with the link can view", and the Drive link is emailed — so external
recipients (without app/network access) can still download.

Provider: **Gmail via OAuth2** (refresh token → access token → Gmail API). Google
Drive uses the same OAuth token (the token must also carry the drive.file scope).
SMTP is supported for small attachments only. All config comes from .env.
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from email.message import EmailMessage

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.email_delivery import EmailDelivery, EmailMethod, EmailStatus
from app.db.models.job import ExtractionJob, ReportMetadata

logger = logging.getLogger(__name__)

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_CHUNK = 8 * 1024 * 1024  # 8 MB (multiple of 256 KB) for resumable upload


class EmailError(Exception):
    pass


# ── Google OAuth2 (shared by Gmail + Drive) ────────────────
_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _google_access_token() -> str:
    import time

    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] - 60 > now:
        return _token_cache["access_token"]
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        if not getattr(settings, name):
            raise EmailError(f"{name} is not configured.")
    resp = requests.post(
        settings.GMAIL_TOKEN_URI,
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "refresh_token": settings.GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not resp.ok:
        raise EmailError(f"Google token exchange failed: {resp.status_code} {resp.text}")
    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
    return _token_cache["access_token"]


# ── Gmail send ─────────────────────────────────────────────
def _gmail_send(msg: EmailMessage) -> str:
    token = _google_access_token()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = requests.post(
        GMAIL_SEND_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"raw": raw},
        timeout=120,
    )
    if not resp.ok:
        raise EmailError(f"Gmail send failed: {resp.status_code} {resp.text}")
    return resp.json().get("id", "")


# ── SMTP (small attachments only) ──────────────────────────
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


def _send_via_provider(msg: EmailMessage) -> str:
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "gmail":
        return _gmail_send(msg)
    if provider == "smtp":
        return _smtp_send(msg)
    raise EmailError(f"Unsupported EMAIL_PROVIDER: {settings.EMAIL_PROVIDER}")


# ── Google Drive upload + share ────────────────────────────
def _drive_upload_and_share(file_path: str, filename: str) -> str:
    """Resumable-upload a file to Drive, share it (anyone-with-link reader), and
    return a shareable view link. Streams in chunks (constant memory)."""
    token = _google_access_token()
    size = os.path.getsize(file_path)

    metadata: dict = {"name": filename}
    if settings.GDRIVE_FOLDER_ID:
        metadata["parents"] = [settings.GDRIVE_FOLDER_ID]

    init = requests.post(
        f"{DRIVE_UPLOAD_URL}?uploadType=resumable&fields=id,webViewLink",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Upload-Content-Type": "application/zip",
            "X-Upload-Content-Length": str(size),
        },
        json=metadata,
        timeout=60,
    )
    if not init.ok:
        raise EmailError(f"Drive upload init failed: {init.status_code} {init.text}")
    session_uri = init.headers.get("Location")
    if not session_uri:
        raise EmailError("Drive upload init did not return a session URI.")

    result: dict = {}
    with open(file_path, "rb") as f:
        uploaded = 0
        while uploaded < size:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            end = uploaded + len(chunk) - 1
            put = requests.put(
                session_uri,
                data=chunk,
                headers={"Content-Range": f"bytes {uploaded}-{end}/{size}"},
                timeout=600,
            )
            if put.status_code in (200, 201):
                result = put.json()
                break
            if put.status_code == 308:  # resume incomplete → next chunk
                uploaded = end + 1
                continue
            raise EmailError(f"Drive upload failed: {put.status_code} {put.text}")

    file_id = result.get("id")
    if not file_id:
        raise EmailError("Drive upload did not return a file id.")

    share = requests.post(
        f"{DRIVE_FILES_URL}/{file_id}/permissions",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "reader", "type": "anyone"},
        timeout=30,
    )
    if not share.ok:
        raise EmailError(f"Drive share failed: {share.status_code} {share.text}")

    return result.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"


# ── Message building ───────────────────────────────────────
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
    summary = (
        f"Job: {job.job_id}\n"
        f"Shortcodes: {codes}\n"
        f"Range: {rng}\n"
        f"Records: {report.csv_row_count:,}\n"
        f"ZIP size: {report.zip_size_bytes / 1048576:.2f} MB\n"
    )

    use_attachment = report.zip_size_bytes <= settings.EMAIL_MAX_ATTACHMENT_BYTES
    delivery.method = EmailMethod.ATTACHMENT if use_attachment else EmailMethod.LINK

    try:
        if use_attachment:
            with open(report.zip_path, "rb") as f:
                data = f.read()
            text = f"Your extraction report is attached.\n\n{summary}"
            html = f"<p>Your extraction report is attached.</p><pre>{summary}</pre>"
            msg = _build_message(
                delivery.recipient, subject, text, html,
                attachment=data, attachment_name=report.zip_filename,
            )
        else:
            link = _drive_upload_and_share(report.zip_path, report.zip_filename)
            text = (
                f"Your extraction report is ready. Download it from Google Drive:\n"
                f"{link}\n\n{summary}"
            )
            html = (
                f"<p>Your extraction report is ready.</p>"
                f'<p><a href="{link}">Download from Google Drive</a></p>'
                f"<pre>{summary}</pre>"
            )
            msg = _build_message(delivery.recipient, subject, text, html)

        message_id = _send_via_provider(msg)
        delivery.status = EmailStatus.SENT
        delivery.provider_message_id = message_id or None
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.error = None
        logger.info("Email SENT for %s to %s (%s)", delivery.job_id, delivery.recipient, delivery.method)
    except Exception as exc:  # noqa: BLE001
        delivery.status = EmailStatus.FAILED
        delivery.error = f"{type(exc).__name__}: {exc}"
        logger.exception("Email FAILED for %s", delivery.job_id)

    db.commit()
    return delivery
