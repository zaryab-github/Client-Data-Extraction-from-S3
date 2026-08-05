"""Phase 6 lightweight tests: Redis/Celery background jobs + job API.

Covers:
  * Job creation (API).
  * Redis queue / Celery task registration.
  * Celery worker execution (via eager mode).
  * Successful extraction.
  * Failed extraction.
  * Status transitions.
  * Ownership (users see only their own jobs unless admin).

Celery runs in eager mode so the task executes in-process — no live Redis needed.
S3 is mocked with moto.
"""

from __future__ import annotations

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
from app.scripts.seed import ensure_rbac, grant_shortcode, upsert_shortcode
from app.services import s3_service
from app.workers.celery_app import celery_app

from fastapi.testclient import TestClient

API = settings.API_V1_PREFIX
PASSWORD = "Passw0rd!"
PW_HASH = hash_password(PASSWORD)  # hash once for all test users

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
RANGE = {"date_from": "2023-09-01T00:00:00", "date_to": "2023-09-01T23:59:59"}


def _add_user(db, email, role_name):
    role = db.scalar(select(Role).where(Role.name == role_name))
    u = User(email=email, hashed_password=PW_HASH, full_name=email, is_active=True, role_id=role.id)
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AWS_REGION", REGION)
    monkeypatch.setattr(settings, "AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setattr(settings, "AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setattr(settings, "S3_BUCKET", BUCKET)
    monkeypatch.setattr(settings, "S3_PREFIX", PREFIX)
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", "")
    monkeypatch.setattr(settings, "CSV_SHORTCODE_COLUMN", "source_addr")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_COLUMN", "created_at")
    monkeypatch.setattr(settings, "CSV_TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S.%f")
    monkeypatch.setattr(settings, "REPORT_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "JOB_ID_STRATEGY", "ext_seq")

    # Run Celery tasks in-process.
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    s3_service.reset_client()

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = get_session_factory()()
    ensure_rbac(db)
    _add_user(db, "admin@example.com", "admin")
    analyst = _add_user(db, "analyst@example.com", "analyst")
    _add_user(db, "other@example.com", "analyst")
    sc = upsert_shortcode(db, "8990", "Client 8990")
    upsert_shortcode(db, "1234", "Client 1234")
    grant_shortcode(db, analyst, sc)
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


# ── Redis queue / task registration ────────────────────────
def test_celery_tasks_registered(env):
    assert "run_extraction_job" in celery_app.tasks
    assert "run_retention" in celery_app.tasks
    assert celery_app.conf.broker_url.startswith("redis://")


# ── Auth required ──────────────────────────────────────────
def test_create_requires_auth(env):
    r = env.client.post(f"{API}/jobs", json={"shortcodes": ["8990"], **RANGE})
    assert r.status_code == 401


# ── Unauthorized shortcode ─────────────────────────────────
def test_create_unauthorized_shortcode(env):
    h = _auth(env.client, "analyst@example.com")
    r = env.client.post(f"{API}/jobs", headers=h, json={"shortcodes": ["1234"], **RANGE})
    assert r.status_code == 403


# ── Job creation + successful extraction + status ──────────
@mock_aws
def test_create_success_and_complete(env):
    _seed_s3()
    h = _auth(env.client, "analyst@example.com")
    r = env.client.post(f"{API}/jobs", headers=h, json={"shortcodes": ["8990"], **RANGE})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert job_id.startswith("EXT-")

    g = env.client.get(f"{API}/jobs/{job_id}", headers=h)
    assert g.status_code == 200
    body = g.json()
    assert body["status"] == "COMPLETED"
    assert body["report"]["csv_row_count"] == 3


# ── Failed extraction ──────────────────────────────────────
@mock_aws
def test_failed_extraction(env, monkeypatch):
    _seed_s3()
    # Column that doesn't exist → extraction raises → job FAILED.
    monkeypatch.setattr(settings, "CSV_SHORTCODE_COLUMN", "no_such_column")
    h = _auth(env.client, "analyst@example.com")
    r = env.client.post(f"{API}/jobs", headers=h, json={"shortcodes": ["8990"], **RANGE})
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    g = env.client.get(f"{API}/jobs/{job_id}", headers=h).json()
    assert g["status"] == "FAILED"
    assert g["error_message"]


# ── Ownership ──────────────────────────────────────────────
@mock_aws
def test_job_ownership(env):
    _seed_s3()
    ha = _auth(env.client, "analyst@example.com")
    job_id = env.client.post(
        f"{API}/jobs", headers=ha, json={"shortcodes": ["8990"], **RANGE}
    ).json()["job_id"]

    ho = _auth(env.client, "other@example.com")
    assert env.client.get(f"{API}/jobs/{job_id}", headers=ho).status_code == 404

    hadm = _auth(env.client, "admin@example.com")
    assert env.client.get(f"{API}/jobs/{job_id}", headers=hadm).status_code == 200


@mock_aws
def test_job_logs(env):
    _seed_s3()
    h = _auth(env.client, "analyst@example.com")
    job_id = env.client.post(
        f"{API}/jobs", headers=h, json={"shortcodes": ["8990"], **RANGE}
    ).json()["job_id"]

    logs = env.client.get(f"{API}/jobs/{job_id}/logs", headers=h)
    assert logs.status_code == 200
    lines = logs.json()
    assert len(lines) > 0
    text = " ".join(l["message"] for l in lines).lower()
    assert "started" in text and "complete" in text

    # incremental fetch returns nothing new when after_id = last id
    last_id = lines[-1]["id"]
    more = env.client.get(f"{API}/jobs/{job_id}/logs?after_id={last_id}", headers=h).json()
    assert more == []


@mock_aws
def test_list_own_only(env):
    _seed_s3()
    ha = _auth(env.client, "analyst@example.com")
    env.client.post(f"{API}/jobs", headers=ha, json={"shortcodes": ["8990"], **RANGE})

    assert len(env.client.get(f"{API}/jobs", headers=ha).json()) == 1
    ho = _auth(env.client, "other@example.com")
    assert env.client.get(f"{API}/jobs", headers=ho).json() == []
    hadm = _auth(env.client, "admin@example.com")
    assert len(env.client.get(f"{API}/jobs", headers=hadm).json()) >= 1
