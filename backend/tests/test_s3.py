"""Phase 3 lightweight tests: AWS S3 integration (mocked with moto — no live AWS).

Covers:
  * S3 authentication (HeadBucket).
  * List files.
  * Date-based file selection.
  * Missing file handling.
  * Invalid S3 configuration handling.
"""

from __future__ import annotations

from datetime import date

import boto3
import pytest
from moto import mock_aws

from app.config import settings
from app.services import s3_service

BUCKET = "test-bucket"
PREFIX = "daily-jasminfiles-fatib"
REGION = "us-east-1"


@pytest.fixture()
def s3_config(monkeypatch):
    monkeypatch.setattr(settings, "AWS_REGION", REGION)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setattr(settings, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(settings, "S3_PREFIX", PREFIX)
    monkeypatch.setattr(settings, "S3_FILE_TEMPLATE", "daily-data_{yyyy}-{mm}-{dd}.csv")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    s3_service.reset_client()
    yield
    s3_service.reset_client()


def _seed(days: list[date]) -> None:
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    for d in days:
        key = f"{PREFIX}/daily-data_{d.isoformat()}.csv"
        client.put_object(Bucket=BUCKET, Key=key, Body=b"source_addr,msg\n8990,hi\n")


# ── S3 authentication ──────────────────────────────────────
@mock_aws
def test_s3_authentication(s3_config):
    _seed([date(2023, 9, 1)])
    assert s3_service.check_connection() is True


@mock_aws
def test_s3_authentication_missing_bucket(s3_config):
    # Bucket never created → HeadBucket fails → S3AccessError.
    with pytest.raises(s3_service.S3AccessError):
        s3_service.check_connection()


# ── Invalid configuration ──────────────────────────────────
def test_invalid_config_missing_bucket(monkeypatch):
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    s3_service.reset_client()
    with pytest.raises(s3_service.S3ConfigError):
        s3_service.discover_files(date(2023, 9, 1), date(2023, 9, 2))


# ── List files + date-based selection ──────────────────────
@mock_aws
@pytest.mark.parametrize("mode", ["template", "list"])
def test_list_and_date_selection(s3_config, mode):
    _seed([date(2023, 9, 1), date(2023, 9, 2), date(2023, 9, 3), date(2023, 9, 5)])
    result = s3_service.discover_files(
        date(2023, 9, 1), date(2023, 9, 5), mode=mode
    )
    found = sorted(f.file_date for f in result.files)
    assert found == [date(2023, 9, 1), date(2023, 9, 2), date(2023, 9, 3), date(2023, 9, 5)]
    # 09-04 is absent → reported missing, not an error.
    assert result.missing_dates == [date(2023, 9, 4)]
    assert all(f.key.startswith(PREFIX + "/") for f in result.files)


@mock_aws
@pytest.mark.parametrize("mode", ["template", "list"])
def test_narrow_range_selects_subset(s3_config, mode):
    _seed([date(2023, 9, 1), date(2023, 9, 2), date(2023, 9, 3), date(2023, 9, 5)])
    result = s3_service.discover_files(
        date(2023, 9, 2), date(2023, 9, 3), mode=mode
    )
    found = sorted(f.file_date for f in result.files)
    assert found == [date(2023, 9, 2), date(2023, 9, 3)]
    assert result.missing_dates == []


# ── Multi-part files per day ───────────────────────────────
@mock_aws
@pytest.mark.parametrize("mode", ["template", "list"])
def test_multipart_files_per_day(s3_config, mode):
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    keys = [
        f"{PREFIX}/daily-data_2023-09-01.csv",
        f"{PREFIX}/daily-data_2023-09-01-part2.csv",
        f"{PREFIX}/daily-data_2023-09-01-part3.csv",
        f"{PREFIX}/daily-data_2023-09-02.csv",
    ]
    for k in keys:
        client.put_object(Bucket=BUCKET, Key=k, Body=b"x")

    result = s3_service.discover_files(date(2023, 9, 1), date(2023, 9, 2), mode=mode)
    assert result.found_count == 4          # all parts discovered
    assert result.missing_dates == []
    day1 = [f for f in result.files if f.file_date == date(2023, 9, 1)]
    assert len(day1) == 3                    # base + part2 + part3


# ── Missing file handling ──────────────────────────────────
@mock_aws
@pytest.mark.parametrize("mode", ["template", "list"])
def test_missing_files_no_crash(s3_config, mode):
    _seed([])  # bucket exists but no daily files
    result = s3_service.discover_files(
        date(2023, 9, 1), date(2023, 9, 3), mode=mode
    )
    assert result.found_count == 0
    assert result.missing_dates == [
        date(2023, 9, 1),
        date(2023, 9, 2),
        date(2023, 9, 3),
    ]


@mock_aws
def test_invalid_date_range(s3_config):
    _seed([date(2023, 9, 1)])
    with pytest.raises(ValueError):
        s3_service.discover_files(date(2023, 9, 5), date(2023, 9, 1))
