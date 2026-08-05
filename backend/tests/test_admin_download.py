"""Phase 7 backend tests: report download + admin management APIs."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.role import Role
from app.db.models.user import User
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.scripts.seed import ensure_rbac
from app.services import s3_service
from app.workers.celery_app import celery_app

from fastapi.testclient import TestClient

API = settings.API_V1_PREFIX
PASSWORD = "Passw0rd!"
PW_HASH = hash_password(PASSWORD)
BUCKET, PREFIX, REGION = "test-bucket", "daily-jasminfiles-fatib", "us-east-1"
HEADER = "_id,source_addr,created_at,short_message"
DAY1 = "\n".join([HEADER, "1,8990,2023-09-01 08:00:00.000,msgA", "2,8990,2023-09-01 18:00:00.000,msgB", ""])
RANGE = {"date_from": "2023-09-01T00:00:00", "date_to": "2023-09-01T23:59:59"}


def _add_user(db, email, role_name):
    role = db.scalar(select(Role).where(Role.name == role_name))
    u = User(email=email, hashed_password=PW_HASH, full_name=email, is_active=True, role_id=role.id)
    db.add(u); db.flush()
    return u


@pytest.fixture()
def env(monkeypatch, tmp_path):
    for k, v in {
        "AWS_REGION": REGION, "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
        "S3_BUCKET": BUCKET, "S3_PREFIX": PREFIX, "S3_ENDPOINT_URL": "",
        "CSV_SHORTCODE_COLUMN": "source_addr", "CSV_TIMESTAMP_COLUMN": "created_at",
        "CSV_TIMESTAMP_FORMAT": "%Y-%m-%d %H:%M:%S.%f", "REPORT_STORAGE_PATH": str(tmp_path),
        "JOB_ID_STRATEGY": "ext_seq",
    }.items():
        monkeypatch.setattr(settings, k, v)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    s3_service.reset_client()

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = get_session_factory()()
    ensure_rbac(db)
    _add_user(db, "admin@example.com", "admin")
    _add_user(db, "analyst@example.com", "analyst")
    db.commit()

    client = TestClient(app)
    yield SimpleNamespace(db=db, client=client)
    db.close()
    celery_app.conf.task_always_eager = False
    s3_service.reset_client()


def _seed_s3():
    c = boto3.client("s3", region_name=REGION)
    c.create_bucket(Bucket=BUCKET)
    c.put_object(Bucket=BUCKET, Key=f"{PREFIX}/daily-data_2023-09-01.csv", Body=DAY1.encode())


def _auth(client, email):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _grant_and_job(client, admin_h, analyst_h):
    # Admin registers + grants shortcode 8990 to analyst, analyst creates a job.
    client.post(f"{API}/admin/shortcodes", headers=admin_h, json={"code": "8990", "name": "C8990"})
    analyst_id = next(u["id"] for u in client.get(f"{API}/admin/users", headers=admin_h).json()
                      if u["email"] == "analyst@example.com")
    client.post(f"{API}/admin/users/{analyst_id}/shortcodes", headers=admin_h, json={"shortcodes": ["8990"]})
    r = client.post(f"{API}/jobs", headers=analyst_h, json={"shortcodes": ["8990"], **RANGE})
    return r.json()["job_id"]


# ── Admin: non-admin rejected ──────────────────────────────
def test_admin_requires_permission(env):
    h = _auth(env.client, "analyst@example.com")
    assert env.client.get(f"{API}/admin/users", headers=h).status_code == 403
    assert env.client.get(f"{API}/admin/shortcodes", headers=h).status_code == 403


# ── Admin: create shortcode + grant enables extraction ─────
@mock_aws
def test_admin_grant_enables_extraction(env):
    _seed_s3()
    admin_h = _auth(env.client, "admin@example.com")
    analyst_h = _auth(env.client, "analyst@example.com")

    # Before grant: analyst cannot use 8990 (must register + grant first).
    r0 = env.client.post(f"{API}/jobs", headers=analyst_h, json={"shortcodes": ["8990"], **RANGE})
    assert r0.status_code == 403

    job_id = _grant_and_job(env.client, admin_h, analyst_h)
    assert job_id.startswith("EXT-")
    got = env.client.get(f"{API}/jobs/{job_id}", headers=analyst_h).json()
    assert got["status"] == "COMPLETED"
    assert got["report"]["csv_row_count"] == 2


# ── Admin: create user + list ──────────────────────────────
def test_admin_create_user(env):
    admin_h = _auth(env.client, "admin@example.com")
    r = env.client.post(f"{API}/admin/users", headers=admin_h, json={
        "email": "new@example.com", "password": "Secret123!", "role": "viewer"})
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"
    emails = [u["email"] for u in env.client.get(f"{API}/admin/users", headers=admin_h).json()]
    assert "new@example.com" in emails


# ── Report download ────────────────────────────────────────
@mock_aws
def test_report_download(env):
    _seed_s3()
    admin_h = _auth(env.client, "admin@example.com")
    analyst_h = _auth(env.client, "analyst@example.com")
    job_id = _grant_and_job(env.client, admin_h, analyst_h)

    # Owner downloads the ZIP.
    r = env.client.get(f"{API}/reports/{job_id}/download", headers=analyst_h)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert "extracted_data.csv" in zf.namelist()

    # A different (non-owner) user gets 404.
    env.client.post(f"{API}/admin/users", headers=admin_h, json={
        "email": "other@example.com", "password": PASSWORD, "role": "analyst"})
    other_h = _auth(env.client, "other@example.com")
    assert env.client.get(f"{API}/reports/{job_id}/download", headers=other_h).status_code == 404


# ── Audit logs recorded ────────────────────────────────────
@mock_aws
def test_audit_logs(env):
    _seed_s3()
    admin_h = _auth(env.client, "admin@example.com")
    analyst_h = _auth(env.client, "analyst@example.com")
    _grant_and_job(env.client, admin_h, analyst_h)

    logs = env.client.get(f"{API}/admin/audit-logs", headers=admin_h).json()
    actions = {row["action"] for row in logs}
    assert "job.create" in actions
