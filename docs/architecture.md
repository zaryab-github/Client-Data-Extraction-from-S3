# Architecture & Complete Flow

How the Client Data Extraction & Delivery System is built and how a request flows
through it end to end. For the phase-by-phase build order see
[development_phases.md](development_phases.md); for what's implemented see
[features.md](features.md).

---

## 1. Purpose

Authenticated users extract client message/event records from **daily CSV files in
AWS S3** over a chosen **date/time range**, filtered by one or more **shortcodes**
(the `source_addr` column) and optionally by **destination numbers** (`destination_addr`).
The result is a combined CSV, packaged as a ZIP with a metadata file, delivered by
**download** or **email**.

**Ground rules**
- Everything configurable comes from `.env` — no hardcoded secrets/URLs/credentials.
- **S3 is read-only** (no write/delete code paths).
- The database stores **application metadata only** — never client CSV data.
- The backend independently enforces authentication and every permission.

---

## 2. Components

```
                               Browser  (http://<SERVER_IP>)
                                    │
                                    ▼
                            ┌───────────────┐
                            │   nginx  :80  │
                            └──────┬────────┘
                     ┌─────────────┴──────────────┐
              /  →   ▼                      /api/  ▼
                ┌──────────────┐            ┌──────────────────┐
                │  frontend    │            │  api (FastAPI)   │
                │ Next.js :3000│            │      :8000       │
                └──────────────┘            └───────┬──────────┘
                    ┌─────────────────┬─────────────┼───────────────┐
                    ▼                 ▼             ▼                │
              ┌───────────┐    ┌────────────┐  ┌──────────────┐     │
              │ Postgres  │    │   Redis    │  │   AWS S3     │     │
              │ metadata  │    │  broker    │  │ (read-only)  │     │
              └───────────┘    └─────┬──────┘  └──────┬───────┘     │
                                     │ task           │ stream      │
                              ┌──────▼───────┐        │             │
                              │ Celery worker│◀───────┘             │
                              │  + beat      │                      │
                              └──────┬───────┘                      │
                                     │ writes                       │
                              ┌──────▼─────────────┐                │
                              │  local storage     │                │
                              │  jobs/<job_id>/     │                │
                              └───┬────────────┬───┘                │
                        download  ▼            ▼  email (Gmail)      │
                          (streamed ZIP)   attach / Drive link      │
   status + live logs ◀───────────────────────────────────────────┘
```

| Component | Role |
|-----------|------|
| **nginx** | Reverse proxy on port 80. `/` → frontend, `/api/` → api. Re-resolves upstreams via Docker DNS. |
| **frontend** (Next.js) | Login, dashboard, extract form, job status + live log console, history, downloads, email, admin screens. |
| **api** (FastAPI) | Auth, RBAC + shortcode authorization, job intake, downloads, admin/email APIs. Thin — never does the heavy scan. |
| **Postgres** | Application metadata: users, roles, permissions, shortcodes, grants, jobs, report metadata, email deliveries, job logs, audit logs. |
| **Redis** | Celery broker + result backend; login rate-limit + token denylist. |
| **worker** (Celery) | Runs the streaming extraction; builds ZIP; sends email (Gmail/Drive). |
| **beat** (Celery) | Schedules retention cleanup. |
| **AWS S3** | Read-only source of truth for the daily CSV files. |
| **local storage** | Generated CSV/ZIP/`metadata.json` per job (a Docker volume shared by api + worker). |

Container details: [docker-compose.md](docker-compose.md).

---

## 3. The S3 data & extraction model

- Files live under one prefix, one (or more) per day:
  `s3://<bucket>/<prefix>/daily-data_YYYY-MM-DD.csv`
- **A day can be split into multiple parts:** `daily-data_2026-08-02.csv`,
  `daily-data_2026-08-02-part2.csv`, … — **all** parts are discovered and processed.
- The **shortcode is a value inside the CSV** — the `source_addr` column (e.g. `8890`),
  not a folder. The date range selects which files to scan; `source_addr` selects which
  rows to keep. An optional `destination_addr` filter narrows further.
- Files are **large** (~100–700 MB each; several GB per multi-day range), so the engine
  **streams row-by-row from S3** with constant memory and writes matches straight to
  disk. Rows whose timestamp (`created_at`) is missing/unparseable but whose shortcode
  matches are **kept** and counted.

All column names, delimiter, timestamp format, and compression are `.env`-configurable.

---

## 4. Request lifecycle (extraction job)

```
1. Browser → POST /api/v1/jobs { shortcodes, date_from, date_to, destinations? }
2. api: authenticate (JWT) → check RBAC (job:create) → check every shortcode is granted
        → validate range → create ExtractionJob (status=PENDING, Job ID EXT-YYYYMMDD-NNNNNN)
        → enqueue Celery task → return 202 { job_id } immediately
3. worker: status=PROCESSING → discover in-range S3 files (all parts)
        → stream each file, filter by source_addr [+ destination_addr] and created_at range
        → append matches to extracted_data.csv (temp dir), logging progress to job_logs
        → build <job_id>.zip + metadata.json, sha256 checksum
        → atomically publish temp dir → jobs/<job_id>/ ; insert ReportMetadata
        → status=COMPLETED (or PARTIAL/FAILED); logs "COMPLETED"
4. Browser polls GET /api/v1/jobs/{id} (+ /logs) → shows live status, log console, report
5. Download: GET /reports/{id}/download-token → native browser download of the ZIP
   Email:    POST /reports/{id}/email → worker sends via Gmail (attachment or Drive link)
```

**Statuses:** `PENDING → PROCESSING → COMPLETED | FAILED` (and `EXPIRED` after retention).

---

## 5. Security model

- **Authentication** — JWT (short access token + rotating refresh cookie), argon2id
  passwords, logout denylist, login rate-limiting, UI idle-timeout auto-logout.
- **Authorization (two layers, backend-enforced)** — RBAC (role→permissions) **and**
  shortcode-level grants; ownership checks on jobs/reports (non-owner → 404).
- **Roles** — `admin` (manage everything, all shortcodes, all jobs), `analyst` (create
  jobs for granted shortcodes, download/email, own history), `viewer` (read-only download
  + own history).
- **Downloads** — server resolves the path from the DB (traversal-proof), ownership-
  checked, short-lived signed token, `410` when expired.
- **Audit** — append-only log of logins, logouts, job create/access, downloads, emails,
  and denials.
- Security headers, safe error handling, read-only S3. Full review:
  [security-review.md](security-review.md).

---

## 6. Data stored (metadata only)

`users`, `roles`, `permissions`, `role_permissions`, `shortcodes`,
`user_shortcode_permissions`, `extraction_jobs`, `report_metadata`, `email_deliveries`,
`job_logs`, `audit_logs`. Schema is managed by **Alembic** migrations that run
automatically when the `api` container starts. Generated artifacts (CSV/ZIP/metadata)
live on the local storage volume, referenced by path from `report_metadata`.

---

## 7. Delivery

- **Download** — the browser fetches a short-lived signed link and streams the ZIP
  straight to disk (no in-memory buffering; works for multi-hundred-MB files).
- **Email (Gmail OAuth2)** — small reports (≤ `EMAIL_MAX_ATTACHMENT_BYTES`) are attached;
  large reports are uploaded to **Google Drive**, shared (anyone-with-link), and the
  Drive link is emailed — so external recipients can download. Progress streams into the
  job's live log. Setup: [gmail-drive-setup.md](gmail-drive-setup.md).

- **Retention** — reports expire after `REPORT_RETENTION_DAYS`; a scheduled cleanup
  deletes the artifacts and marks jobs `EXPIRED`. The S3 source is never touched.
