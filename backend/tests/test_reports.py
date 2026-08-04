"""Phase 5 lightweight tests: Job ID + report storage.

Covers:
  * Job ID creation (format + sequential).
  * Job directory creation.
  * CSV creation.
  * ZIP creation.
  * ZIP contains CSV.
  * metadata.json creation.
  * File cleanup (retention).
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select

from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.job import JobStatus, ReportMetadata
from app.db.models.role import Role
from app.db.models.user import User
from app.db.session import get_engine, get_session_factory
from app.scripts.seed import ensure_rbac
from app.services import job_service, retention_service, storage_service
from app.services.extraction_service import ExtractionRequest

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
        "4,8990,BADTIME,msgD",
        "",
    ]
)


@pytest.fixture()
def setup(monkeypatch, tmp_path):
    # S3 + CSV config
    monkeypatch.setattr(settings, "AWS_REGION", REGION)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setattr(settings, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(settings, "S3_PREFIX", PREFIX)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "CSV_SHORTCODE_COLUMN", "source_addr")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_COLUMN", "created_at")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S.%f")
    # storage + retention
    monkeypatch.setattr(settings, "REPORT_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "REPORT_RETENTION_DAYS", 30)
    monkeypatch.setattr(settings, "JOB_ID_STRATEGY", "ext_seq")

    from app.services import s3_service
    s3_service.reset_client()

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = get_session_factory()()
    ensure_rbac(db)
    role = db.scalar(select(Role).where(Role.name == "analyst"))
    user = User(
        email="rep@example.com",
        hashed_password="x",  # not used; these tests don't log in
        full_name="Reporter",
        is_active=True,
        role_id=role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    yield db, user

    db.close()
    s3_service.reset_client()


def _seed_s3():
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    client.put_object(Bucket=BUCKET, Key=f"{PREFIX}/daily-data_2023-09-01.csv", Body=DAY1.encode())


def _req():
    return ExtractionRequest(
        shortcodes=["8990"],
        date_from=datetime(2023, 9, 1, 0, 0, 0),
        date_to=datetime(2023, 9, 1, 23, 59, 59),
    )


# ── Job ID creation (format + sequential) ──────────────────
def test_job_id_creation_sequential(setup):
    db, user = setup
    j1 = job_service.create_job(db, user, _req())
    j2 = job_service.create_job(db, user, _req())
    assert re.match(r"^EXT-\d{8}-\d{6}$", j1.job_id)
    assert re.match(r"^EXT-\d{8}-\d{6}$", j2.job_id)
    seq1 = int(j1.job_id.rsplit("-", 1)[-1])
    seq2 = int(j2.job_id.rsplit("-", 1)[-1])
    assert seq2 == seq1 + 1


# ── Full run: dir, CSV, ZIP, ZIP-contains-CSV, metadata ────
@mock_aws
def test_full_job_artifacts(setup):
    db, user = setup
    _seed_s3()
    job = job_service.create_and_run(db, user, _req())

    assert job.status == JobStatus.COMPLETED
    d = storage_service.job_dir(job.job_id)
    assert d.is_dir()                                          # job directory
    assert (d / "extracted_data.csv").exists()                # CSV creation

    zip_path = d / f"{job.job_id}.zip"
    assert zip_path.exists()                                   # ZIP creation
    with zipfile.ZipFile(zip_path) as zf:
        assert "extracted_data.csv" in zf.namelist()          # ZIP contains CSV

    meta_path = d / "metadata.json"
    assert meta_path.exists()                                  # metadata.json creation
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["job_id"] == job.job_id
    assert meta["records_extracted"] == 3                      # rows A, B, D
    assert meta["user"] == "rep@example.com"
    assert meta["status"] == JobStatus.COMPLETED
    assert set(meta["shortcodes"]) == {"8990"}

    # DB report metadata recorded
    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == job.job_id))
    assert report is not None
    assert report.csv_row_count == 3
    assert report.zip_size_bytes > 0
    assert report.checksum_sha256


# ── File cleanup / retention ───────────────────────────────
@mock_aws
def test_retention_cleanup(setup):
    db, user = setup
    _seed_s3()
    job = job_service.create_and_run(db, user, _req())
    d = storage_service.job_dir(job.job_id)
    assert d.exists()

    # Force the report to be expired.
    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == job.job_id))
    report.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    removed = retention_service.cleanup_expired(db)
    assert removed == 1
    assert not d.exists()                                      # artifacts deleted
    db.refresh(job)
    assert job.status == JobStatus.EXPIRED
