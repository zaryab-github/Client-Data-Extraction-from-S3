"""Read-only AWS S3 service layer.

Responsibilities (Phase 3):
  * Build a boto3 S3 client from .env (region, credentials/IAM role, optional endpoint).
  * Discover the daily CSV files that fall within a date range.
  * Report which expected daily files are missing.

STRICTLY READ-ONLY: this module only ever calls list/head/get operations. There are
no put/delete/copy code paths — source files are never modified or deleted.

Nothing is hardcoded: bucket, prefix, file-name template, region, and credentials
all come from settings (.env). AWS credentials are never exposed to the frontend.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from app.config import settings

logger = logging.getLogger(__name__)


# ── Errors ─────────────────────────────────────────────────
class S3ConfigError(Exception):
    """Raised when required S3 configuration is missing/invalid."""


class S3AccessError(Exception):
    """Raised when S3 cannot be reached or a request fails."""


# ── Result types ───────────────────────────────────────────
@dataclass
class DiscoveredFile:
    key: str
    file_date: date
    size: int | None = None


@dataclass
class DiscoveryResult:
    bucket: str
    prefix: str
    files: list[DiscoveredFile] = field(default_factory=list)
    missing_dates: list[date] = field(default_factory=list)

    @property
    def found_count(self) -> int:
        return len(self.files)

    @property
    def keys(self) -> list[str]:
        return [f.key for f in self.files]


# ── Client (lazy, cached; reset_client() for tests) ────────
_client = None


def _build_client():
    if not settings.S3_BUCKET:
        raise S3ConfigError("S3_BUCKET is not configured (set it in .env).")
    if not settings.AWS_REGION:
        raise S3ConfigError("AWS_REGION is not configured (set it in .env).")

    kwargs: dict = {
        "region_name": settings.AWS_REGION,
        "config": BotoConfig(
            retries={"max_attempts": settings.S3_MAX_RETRIES, "mode": "standard"}
        ),
    }
    # Only use an endpoint override if it is an actual URL (guards against a
    # stray value such as a leftover inline comment in .env).
    endpoint = (settings.S3_ENDPOINT_URL or "").strip()
    if endpoint.startswith(("http://", "https://")):
        kwargs["endpoint_url"] = endpoint

    # Explicit keys are optional — if absent (or clearly not a real value), boto3
    # uses the default chain (e.g. an attached IAM role).
    access_key = (settings.AWS_ACCESS_KEY_ID or "").strip()
    secret_key = (settings.AWS_SECRET_ACCESS_KEY or "").strip()
    if access_key and secret_key and not access_key.startswith("#"):
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def get_client():
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def reset_client() -> None:
    """Drop the cached client (used by tests / after config changes)."""
    global _client
    _client = None


# ── Helpers ────────────────────────────────────────────────
def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _iter_dates(date_from: date | datetime, date_to: date | datetime) -> Iterator[date]:
    start, end = _as_date(date_from), _as_date(date_to)
    if start > end:
        raise ValueError("date_from must be on or before date_to.")
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _expand_template(template: str, d: date) -> str:
    return template.format(yyyy=f"{d.year:04d}", mm=f"{d.month:02d}", dd=f"{d.day:02d}")


def _build_key(prefix: str, filename: str) -> str:
    prefix = (prefix or "").strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def _template_to_regex(template: str) -> re.Pattern[str]:
    """Turn a filename template into a regex with named date groups.

    Allows optional multi-part suffixes (e.g. '-part2', '-part3') between the date
    and the extension, so a day split across multiple files is matched:
        daily-data_2026-08-02.csv
        daily-data_2026-08-02-part2.csv
    """
    if "." in template:
        stem, ext = template.rsplit(".", 1)
        ext_regex = re.escape("." + ext)
    else:
        stem, ext_regex = template, ""
    tmp = stem.replace("{yyyy}", "\x00Y").replace("{mm}", "\x00M").replace("{dd}", "\x00D")
    escaped = re.escape(tmp)
    stem_pattern = (
        escaped.replace("\x00Y", r"(?P<y>\d{4})")
        .replace("\x00M", r"(?P<m>\d{2})")
        .replace("\x00D", r"(?P<d>\d{2})")
    )
    # Zero or more '-token' segments (e.g. -part2) between the date and extension.
    multipart = r"(?:-[A-Za-z0-9]+)*"
    return re.compile(f"^{stem_pattern}{multipart}{ext_regex}$")


def _resolve(bucket, prefix, file_template, mode):
    return (
        bucket or settings.S3_BUCKET,
        settings.S3_PREFIX if prefix is None else prefix,
        file_template or settings.S3_FILE_TEMPLATE,
        (mode or settings.S3_DISCOVERY_MODE).lower(),
    )


# ── Public API ─────────────────────────────────────────────
def check_connection(bucket: str | None = None) -> bool:
    """Verify credentials + bucket reachability via HeadBucket (read-only)."""
    bucket = bucket or settings.S3_BUCKET
    if not bucket:
        raise S3ConfigError("S3_BUCKET is not configured (set it in .env).")
    try:
        get_client().head_bucket(Bucket=bucket)
        return True
    except (NoCredentialsError, EndpointConnectionError) as exc:
        raise S3AccessError(f"S3 not reachable: {exc}") from exc
    except ClientError as exc:
        raise S3AccessError(f"S3 HeadBucket failed for '{bucket}': {exc}") from exc


def get_object_stream(key: str, bucket: str | None = None):
    """Return a streaming body for an object (read-only GetObject).

    The caller is responsible for reading and closing the stream. Used by the
    extraction engine to process large files without loading them into memory.
    """
    bucket = bucket or settings.S3_BUCKET
    if not bucket:
        raise S3ConfigError("S3_BUCKET is not configured (set it in .env).")
    try:
        resp = get_client().get_object(Bucket=bucket, Key=key)
        return resp["Body"]
    except (NoCredentialsError, EndpointConnectionError, BotoCoreError, ClientError) as exc:
        raise S3AccessError(f"GetObject failed for '{bucket}/{key}': {exc}") from exc


def discover_files(
    date_from: date | datetime,
    date_to: date | datetime,
    *,
    prefix: str | None = None,
    file_template: str | None = None,
    bucket: str | None = None,
    mode: str | None = None,
) -> DiscoveryResult:
    """List the daily CSV files in S3 whose date falls within [date_from, date_to].

    `mode`:
      - "template" → build exact keys per day and HeadObject each (fast).
      - "list"     → ListObjectsV2 under the prefix and match by filename (robust).
    """
    bucket, prefix, file_template, mode = _resolve(bucket, prefix, file_template, mode)
    if not bucket:
        raise S3ConfigError("S3_BUCKET is not configured (set it in .env).")

    expected = list(_iter_dates(date_from, date_to))
    logger.info(
        "S3 discovery: bucket=%s prefix=%s days=%d mode=%s",
        bucket, prefix, len(expected), mode,
    )

    if mode == "template":
        result = _discover_template(bucket, prefix, file_template, expected)
    elif mode == "list":
        result = _discover_list(bucket, prefix, file_template, expected)
    else:
        raise S3ConfigError(f"Invalid S3_DISCOVERY_MODE: {mode!r} (use 'list' or 'template').")

    logger.info(
        "S3 discovery result: found=%d missing=%d",
        result.found_count, len(result.missing_dates),
    )
    if result.missing_dates:
        logger.warning(
            "S3 discovery: %d missing daily file(s) in range: %s",
            len(result.missing_dates),
            ", ".join(d.isoformat() for d in result.missing_dates),
        )
    return result


def _discover_template(bucket, prefix, file_template, expected) -> DiscoveryResult:
    """Per-day targeted listing.

    Lists objects under the day-specific prefix (e.g. `.../daily-data_2026-08-02`)
    so ALL of a day's files — base + parts — are discovered, while staying efficient
    (only that day's objects are listed, not the whole bucket).
    """
    client = get_client()
    pattern = _template_to_regex(file_template)
    paginator = client.get_paginator("list_objects_v2")
    res = DiscoveryResult(bucket=bucket, prefix=prefix)

    for d in expected:
        day_stem = _expand_template(file_template, d).rsplit(".", 1)[0]
        day_prefix = _build_key(prefix, day_stem)
        found = False
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=day_prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    filename = key.rsplit("/", 1)[-1]
                    m = pattern.match(filename)
                    if not m:
                        continue
                    try:
                        fd = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
                    except ValueError:
                        continue
                    if fd == d:
                        found = True
                        res.files.append(
                            DiscoveredFile(key=key, file_date=d, size=obj.get("Size"))
                        )
        except (NoCredentialsError, EndpointConnectionError, BotoCoreError, ClientError) as exc:
            raise S3AccessError(
                f"ListObjectsV2 failed for '{bucket}/{day_prefix}': {exc}"
            ) from exc
        if not found:
            res.missing_dates.append(d)

    res.files.sort(key=lambda f: (f.file_date, f.key))
    return res


def _discover_list(bucket, prefix, file_template, expected) -> DiscoveryResult:
    client = get_client()
    pattern = _template_to_regex(file_template)
    wanted = set(expected)
    res = DiscoveryResult(bucket=bucket, prefix=prefix)
    found_dates: set[date] = set()

    list_prefix = (prefix or "").strip("/")
    if list_prefix:
        list_prefix += "/"

    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.rsplit("/", 1)[-1]
                m = pattern.match(filename)
                if not m:
                    continue
                try:
                    d = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
                except ValueError:
                    continue
                if d in wanted:
                    # Collect ALL files for the date (base + parts), not just one.
                    found_dates.add(d)
                    res.files.append(
                        DiscoveredFile(key=key, file_date=d, size=obj.get("Size"))
                    )
    except (NoCredentialsError, EndpointConnectionError, BotoCoreError, ClientError) as exc:
        raise S3AccessError(f"ListObjectsV2 failed for '{bucket}/{list_prefix}': {exc}") from exc

    res.files.sort(key=lambda f: (f.file_date, f.key))
    res.missing_dates = sorted(d for d in wanted if d not in found_dates)
    return res
