"""Phase 9 lightweight security tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

API = settings.API_V1_PREFIX


def test_security_headers_present():
    with TestClient(app) as client:
        r = client.get(f"{API}/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "Referrer-Policy" in r.headers


def test_protected_endpoints_reject_unauthenticated():
    with TestClient(app) as client:
        assert client.get(f"{API}/jobs").status_code == 401
        assert client.get(f"{API}/admin/users").status_code == 401
        assert client.post(f"{API}/jobs", json={}).status_code in (401, 422)


def test_cors_is_not_wildcard():
    # CORS is restricted to configured origins, never "*".
    assert "*" not in settings.cors_origins
