# Security Review (Phase 9)

A verification pass over the whole system against the Phase 9 checklist, plus the
hardening applied in this phase. Status legend: ✅ in place · 🟡 in place with a
recommendation · ⬜ recommended, not enforced by code.

---

## Checklist

| # | Item | Status | Where / notes |
|---|------|--------|---------------|
| 1 | Authentication | ✅ | JWT (short access + rotating refresh, httpOnly cookie), argon2id password hashing, token denylist on logout, login rate-limiting. Idle-timeout auto-logout in the UI. |
| 2 | RBAC | ✅ | `core/rbac.py` role→permission map; `require_permission()` on every protected route. |
| 3 | Shortcode-level authorization | ✅ | `services/authorization.py` — every requested shortcode validated against the user's grants (admins = all); all-or-nothing; denials audited. |
| 4 | Backend permission validation | ✅ | Enforced server-side on every request; the client's claims are never trusted. Ownership checks on jobs/reports (non-owner → 404). |
| 5 | Private / read-only S3 | ✅ 🟡 | Code has **no** S3 write/delete paths (only list/head/get). **Recommendation:** scope the IAM credentials to read-only too (policy below). |
| 6 | No AWS credentials in frontend | ✅ | Frontend only receives `NEXT_PUBLIC_*` (API URL + UI toggles). No AWS/S3 anything. |
| 7 | No hardcoded secrets | ✅ | All secrets/URLs from `.env`; startup fails fast if required ones are missing. |
| 8 | All configuration in `.env` | ✅ | `app/config.py` Pydantic Settings; `.env.example` committed with blanks. |
| 9 | `.env` ignored by Git | ✅ | Root `.gitignore` ignores `.env`, `deploy/.env`, `frontend/.env.local`, certs, storage. |
| 10 | Secure report downloads | ✅ | Path resolved server-side from the DB (traversal-proof), ownership-checked, non-enumerable Job IDs, short-lived signed download token, `410` when expired. |
| 11 | Report retention | ✅ | `retention_service.cleanup_expired` on Celery beat; expired artifacts deleted, jobs marked `EXPIRED`; S3 source untouched. |
| 12 | Audit logs | ✅ | `audit_logs` (append-only): login success/failure, logout, job create/access, report download/email, authz denials — with IP + user-agent. Admin viewer at `/admin/audit`. |
| 13 | Input validation | ✅ | Pydantic on all bodies; date range validated (`from ≤ to`, `MAX_RANGE_DAYS`); shortcode selection validated. |
| 14 | API error handling | ✅ | Consistent `{"detail": …}`; a global handler logs unhandled errors server-side and returns a generic `500` (no internal leakage). |
| 15 | Secure logging | ✅ 🟡 | No secrets/tokens/passwords are logged. **Recommendation:** ship logs to a central store and alert on `authz.deny` / `login.failure` spikes. |
| 16 | Production HTTPS | 🟡 | Currently HTTP over a private IP (documented, intentional). TLS configs provided (`deploy/nginx/app.conf`; self-signed-for-IP and Let's Encrypt paths in `DEPLOYMENT.md`). **Recommendation:** enable TLS before any public exposure. |
| 17 | Rate limiting | ✅ 🟡 | Login rate-limited per email+IP (Redis, best-effort). **Recommendation:** add limits to the n8n `/internal` endpoints in Phase 10. |

---

## Hardening applied in this phase

- **Security headers** on every API response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
  (HSTS is added by the TLS nginx config, since it only applies over HTTPS.)
- **Global exception handler** — unhandled errors are logged server-side and return a
  generic `500` with no stack trace or internals.
- **Auth auditing** — login success, login failure (bad credentials / rate-limited),
  and logout are now recorded in `audit_logs`.
- **API docs toggle** — `ENABLE_API_DOCS` (default true) can hide `/docs`, `/redoc`,
  and `/openapi.json` in production.
- **Lightweight security tests** — headers present, unauthenticated endpoints rejected,
  CORS not wildcard, auth events audited.

---

## Recommended IAM policy (read-only S3)

Attach a policy like this to the credentials/role the app uses, so read-only is
enforced by AWS in addition to the code:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::bk-kannel",
        "arn:aws:s3:::bk-kannel/*"
      ]
    }
  ]
}
```

---

## Remaining recommendations (operational, not code)

- **Run containers as non-root.** The api/worker containers currently run as root
  (Celery even warns about it). To harden, add a non-root user to `backend/Dockerfile`
  and ensure the `report_storage` volume is writable by that user (chown the mount /
  recreate the volume). Deferred here to avoid disrupting the running deployment.
- **Enable TLS** (self-signed for the IP, or Let's Encrypt with a domain) before any
  exposure beyond the trusted network — JWTs currently travel over plain HTTP.
- **Secrets management** — prefer a secrets manager (or at least tight file perms on
  `.env`) over plaintext `.env` on disk in production.
- **Dependency scanning** — run `pip-audit` / `npm audit` and a secret scanner in CI.
- **Download links in URLs** — the in-app download and Drive links carry a capability
  token in the URL. These are short-lived (download token) or Drive-managed; they are
  not personal data, but avoid forwarding them where URL logs are sensitive.
