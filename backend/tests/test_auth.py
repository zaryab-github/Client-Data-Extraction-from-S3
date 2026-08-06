"""Phase 2 lightweight tests: authentication + authorization.

Covers:
  * Valid login.
  * Invalid login rejection.
  * Unauthenticated API rejection.
  * Authorized shortcode access.
  * Unauthorized shortcode rejection.

Uses SQLite (from conftest) with tables created directly and seeded via the
reusable seed helpers. No live Postgres/Redis required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401 - register models on metadata
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.scripts.seed import (
    ensure_rbac,
    grant_shortcode,
    upsert_shortcode,
    upsert_user,
)

API = settings.API_V1_PREFIX
PASSWORD = "Passw0rd!"
ADMIN = "admin@example.com"
ANALYST = "analyst@example.com"
VIEWER = "viewer@example.com"


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session = get_session_factory()()
    try:
        ensure_rbac(session)
        admin = upsert_user(session, ADMIN, PASSWORD, "admin", "Admin")
        analyst = upsert_user(session, ANALYST, PASSWORD, "analyst", "Analyst")
        upsert_user(session, VIEWER, PASSWORD, "viewer", "Viewer")

        sc_8990 = upsert_shortcode(session, "8990", "Client 8990")
        upsert_shortcode(session, "1234", "Client 1234")

        # Analyst is granted ONLY 8990.
        grant_shortcode(session, analyst, sc_8990, granted_by=admin)
        session.commit()
    finally:
        session.close()

    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def _auth_headers(client: TestClient, email: str) -> dict:
    r = _login(client, email)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Valid login ────────────────────────────────────────────
def test_valid_login(client):
    r = _login(client, ANALYST)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == ANALYST
    assert body["user"]["role"] == "analyst"
    assert "job:create" in body["user"]["permissions"]


# ── Invalid login rejection ────────────────────────────────
def test_invalid_login_wrong_password(client):
    r = _login(client, ANALYST, "wrong-password")
    assert r.status_code == 401


def test_invalid_login_unknown_user(client):
    r = _login(client, "nobody@example.com")
    assert r.status_code == 401


# ── Unauthenticated API rejection ──────────────────────────
def test_unauthenticated_me_rejected(client):
    assert client.get(f"{API}/auth/me").status_code == 401


def test_unauthenticated_shortcodes_rejected(client):
    assert client.get(f"{API}/shortcodes").status_code == 401


def test_bad_token_rejected(client):
    r = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


# ── Authorized shortcode access ────────────────────────────
def test_analyst_sees_only_granted_shortcodes(client):
    headers = _auth_headers(client, ANALYST)
    r = client.get(f"{API}/shortcodes", headers=headers)
    assert r.status_code == 200
    codes = sorted(s["code"] for s in r.json())
    assert codes == ["8990"]


def test_analyst_can_access_authorized_shortcode(client):
    headers = _auth_headers(client, ANALYST)
    assert client.get(f"{API}/shortcodes/8990", headers=headers).status_code == 200
    r = client.post(
        f"{API}/shortcodes/check", headers=headers, json={"shortcodes": ["8990"]}
    )
    assert r.status_code == 200
    assert r.json()["authorized"] is True


def test_admin_sees_all_shortcodes(client):
    headers = _auth_headers(client, ADMIN)
    r = client.get(f"{API}/shortcodes", headers=headers)
    assert r.status_code == 200
    codes = sorted(s["code"] for s in r.json())
    assert codes == ["1234", "8990"]


# ── Unauthorized shortcode rejection ───────────────────────
def test_analyst_denied_unauthorized_shortcode_get(client):
    headers = _auth_headers(client, ANALYST)
    assert client.get(f"{API}/shortcodes/1234", headers=headers).status_code == 403


def test_analyst_denied_unauthorized_shortcode_check(client):
    headers = _auth_headers(client, ANALYST)
    r = client.post(
        f"{API}/shortcodes/check", headers=headers, json={"shortcodes": ["8990", "1234"]}
    )
    assert r.status_code == 403


def test_viewer_has_no_shortcodes(client):
    headers = _auth_headers(client, VIEWER)
    r = client.get(f"{API}/shortcodes", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


# ── Audit logging of auth events (Phase 9) ─────────────────
def test_failed_login_is_audited(client):
    from sqlalchemy import select

    from app.db.models.audit import AuditLog
    from app.db.session import get_session_factory

    _login(client, ANALYST, "definitely-wrong")
    session = get_session_factory()()
    try:
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "login.failure")
        ).all()
        assert len(rows) >= 1
    finally:
        session.close()


def test_successful_login_is_audited(client):
    from sqlalchemy import select

    from app.db.models.audit import AuditLog
    from app.db.session import get_session_factory

    _login(client, ADMIN)
    session = get_session_factory()()
    try:
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "login.success")
        ).all()
        assert len(rows) >= 1
    finally:
        session.close()
