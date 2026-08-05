"""Phase 4 lightweight tests: CSV extraction engine (mocked S3 via moto).

Covers:
  * One CSV.
  * Multiple CSVs.
  * One shortcode.
  * Multiple shortcodes.
  * Date filtering.
  * Date/time filtering.
  * No matching records.
  * Bad-timestamp rows are kept (agreed policy).

Streaming path is exercised end-to-end: objects live in a mocked S3 and are read
through s3_service.get_object_stream + the extraction engine.
"""

from __future__ import annotations

import csv
from datetime import datetime

import boto3
import pytest
from moto import mock_aws

from app.config import settings
from app.services import s3_service
from app.services.extraction_service import ExtractionRequest, run_extraction

BUCKET = "test-bucket"
PREFIX = "daily-jasminfiles-fatib"
REGION = "us-east-1"
HEADER = "_id,source_addr,created_at,short_message"

DAY1 = "\n".join(
    [
        HEADER,
        "1,8990,2023-09-01 08:00:00.000,msgA",
        "2,8990,2023-09-01 18:00:00.000,msgB",
        "3,1234,2023-09-01 09:00:00.000,msgC",
        "4,8990,BADTIME,msgD",  # matching shortcode, unparseable timestamp
        "",
    ]
)
DAY2 = "\n".join(
    [
        HEADER,
        "5,8990,2023-09-02 10:00:00.000,msgE",
        "6,1234,2023-09-02 11:00:00.000,msgF",
        "",
    ]
)


@pytest.fixture()
def s3_config(monkeypatch):
    monkeypatch.setattr(settings, "AWS_REGION", REGION)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setattr(settings, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(settings, "S3_PREFIX", PREFIX)
    monkeypatch.setattr(settings, "S3_FILE_TEMPLATE", "daily-data_{yyyy}-{mm}-{dd}.csv")
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "CSV_SHORTCODE_COLUMN", "source_addr")
    monkeypatch.setattr(settings, "CSV_DELIMITER", ",")
    monkeypatch.setattr(settings, "CSV_HAS_HEADER", True)
    monkeypatch.setattr(settings, "CSV_COMPRESSION", "none")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_COLUMN", "created_at")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S.%f")
    s3_service.reset_client()
    yield
    s3_service.reset_client()


def _seed():
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    client.put_object(Bucket=BUCKET, Key=f"{PREFIX}/daily-data_2023-09-01.csv", Body=DAY1.encode())
    client.put_object(Bucket=BUCKET, Key=f"{PREFIX}/daily-data_2023-09-02.csv", Body=DAY2.encode())


def _read_output(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]
    ids = [r[0] for r in data]
    return header, ids


def _req(shortcodes, d_from, d_to):
    return ExtractionRequest(shortcodes=shortcodes, date_from=d_from, date_to=d_to)


# ── One CSV, one shortcode ─────────────────────────────────
@mock_aws
def test_one_csv_one_shortcode(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    stats = run_extraction(
        _req(["8990"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 1, 23, 59, 59)),
        str(out),
    )
    header, ids = _read_output(out)
    assert header == HEADER.split(",")            # all columns preserved
    assert sorted(ids) == ["1", "2", "4"]          # A, B, D (D has bad ts → kept)
    assert stats.files_processed == 1
    assert stats.rows_matched == 3
    assert stats.bad_timestamp_rows == 1


# ── Multiple CSVs ──────────────────────────────────────────
@mock_aws
def test_multiple_csvs(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    stats = run_extraction(
        _req(["8990"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 2, 23, 59, 59)),
        str(out),
    )
    _, ids = _read_output(out)
    assert sorted(ids) == ["1", "2", "4", "5"]     # day1 A,B,D + day2 E
    assert stats.files_processed == 2
    assert stats.rows_matched == 4


# ── Multiple shortcodes ────────────────────────────────────
@mock_aws
def test_multiple_shortcodes(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    stats = run_extraction(
        _req(["8990", "1234"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 2, 23, 59, 59)),
        str(out),
    )
    _, ids = _read_output(out)
    assert sorted(ids) == ["1", "2", "3", "4", "5", "6"]
    assert stats.rows_matched == 6


# ── Date filtering (whole-day range excludes day2) ─────────
@mock_aws
def test_date_filtering(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    run_extraction(
        _req(["8990", "1234"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 1, 23, 59, 59)),
        str(out),
    )
    _, ids = _read_output(out)
    assert sorted(ids) == ["1", "2", "3", "4"]     # only day1; day2 file not in range


# ── Date/time filtering (sub-day window) ───────────────────
@mock_aws
def test_datetime_filtering(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    stats = run_extraction(
        _req(["8990", "1234"], datetime(2023, 9, 1, 8, 30, 0), datetime(2023, 9, 1, 12, 0, 0)),
        str(out),
    )
    _, ids = _read_output(out)
    # A(08:00) excluded, B(18:00) excluded, C(09:00) included, D(bad ts) kept.
    assert sorted(ids) == ["3", "4"]
    assert stats.bad_timestamp_rows == 1


# ── Destination filter ─────────────────────────────────────
@mock_aws
def test_destination_filter(s3_config, tmp_path):
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    header = "_id,source_addr,destination_addr,created_at,short_message"
    body = "\n".join([
        header,
        "1,8990,923000000001,2023-09-01 08:00:00.000,a",
        "2,8990,923000000002,2023-09-01 09:00:00.000,b",
        "3,8990,923000000001,2023-09-01 10:00:00.000,c",
        "",
    ])
    client.put_object(Bucket=BUCKET, Key=f"{PREFIX}/daily-data_2023-09-01.csv", Body=body.encode())

    out = tmp_path / "out.csv"
    stats = run_extraction(
        ExtractionRequest(
            ["8990"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 1, 23, 59, 59),
            destinations=["923000000001"],
        ),
        str(out),
    )
    _, ids = _read_output(out)
    assert sorted(ids) == ["1", "3"]  # only rows with that destination_addr
    assert stats.rows_matched == 2


# ── No matching records ────────────────────────────────────
@mock_aws
def test_no_matching_records(s3_config, tmp_path):
    _seed()
    out = tmp_path / "out.csv"
    stats = run_extraction(
        _req(["9999"], datetime(2023, 9, 1, 0, 0, 0), datetime(2023, 9, 2, 23, 59, 59)),
        str(out),
    )
    header, ids = _read_output(out)
    assert header == HEADER.split(",")             # header still written
    assert ids == []                                # no data rows
    assert stats.rows_matched == 0
