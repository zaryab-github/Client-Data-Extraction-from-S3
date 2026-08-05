# Features & Roadmap

A living catalogue of what the Client Data Extraction & Delivery System does today,
what's planned, and the operational tools available. See
[application-workflow.md](application-workflow.md) for the end-to-end design and
[development_phases.md](../development_phases.md) for the phase plan.

Last updated: after Phase 7 (Frontend Dashboard & Admin Management).

---

## ✅ Delivered

### Authentication & accounts (Phase 2)
- Email/password login with JWT (short-lived access token + rotating refresh cookie).
- Passwords hashed with argon2id. Login rate-limiting (Redis, best-effort).
- Logout with token denylist.

### Authorization (Phase 2)
- **RBAC** — roles `admin` / `analyst` / `viewer`, each mapped to permission codes.
- **Shortcode-level access** — a user may only extract shortcodes explicitly granted
  to them (admins are authorized for all *registered* shortcodes).
- Every permission is validated on the **backend** on every request; the UI only
  reflects it. Denied attempts are audit-logged.

### S3 source integration (Phase 3, + multi-part days)
- Read-only discovery of the daily CSV files that fall in a date range.
- **Multi-part days supported:** a single day split across files (`daily-data_DATE.csv`,
  `daily-data_DATE-part2.csv`, …) is fully discovered — **all** parts are processed.
- Two discovery modes (`list` = one bucket listing; `template` = efficient per-day
  targeted listing), configurable via `.env`. Both handle parts.
- Missing daily files are reported (not fatal). S3 is never modified or deleted.
- The exact **list of files scanned** for a job is recorded and shown in the UI, so you
  can verify which parts were included.

### CSV extraction engine (Phase 4, + destination filter)
- Streams each daily file from S3 **row by row** (constant memory) — safe for the
  real 100–236 MB/day files.
- Keeps rows where the shortcode column (`source_addr`) matches **and** the timestamp
  column (`created_at`) is within range. Rows with a missing/unparseable timestamp are
  **kept** and counted.
- **Optional destination filter:** narrow results to specific `destination_addr`
  values (MSISDNs). Column configurable via `CSV_DESTINATION_COLUMN`; per-job values
  stored on the job and shown in the UI.
- Preserves all original columns; combines matches from all files into one CSV.

### Reports: Job ID, storage, packaging (Phase 5)
- Unique human-friendly **Job ID** `EXT-YYYYMMDD-NNNNNN`.
- Per-job local storage: `extracted_data.csv`, `{job_id}.zip`, `metadata.json`.
- Atomic write (temp → publish); sha256 checksum; DB report metadata.
- Configurable **retention** with automatic cleanup of expired reports.

### Background processing (Phase 6)
- Extraction runs **asynchronously** in a Celery worker (Redis broker) — the API
  returns a Job ID instantly.
- Statuses: `PENDING → PROCESSING → COMPLETED / FAILED` (and `EXPIRED`).
- Idempotent tasks; retention cleanup scheduled on Celery beat.
- **Audit log** of logins, job creation/access, downloads, and denials.

### Web app + admin (Phase 7, + extras)
- **Dashboard** with stat tiles and recent jobs.
- **Extract** screen: authorized-shortcode multi-select + date/time range +
  optional destination filter → Generate.
- **Job status** page: live polling with a status badge; a **live log console**
  (real-time per-job progress); **ZIP download**; "files scanned" list; clear
  "no source files found" notice.
- **History** with status filter and per-job download.
- **Admin** screens: register/list **shortcodes** + grant access; full **user
  management** (create, change role, activate/deactivate, reset password, delete);
  view **audit logs**.
- Modern tabbed UI, dark theme, colored status badges.

### Roles (RBAC)
| Role | Purpose |
|------|---------|
| **admin** | Manage users/roles/shortcodes/grants, view audit; authorized for all shortcodes; sees all jobs. |
| **analyst** | Create extraction jobs (granted shortcodes only), download/email reports, view own history. |
| **viewer** | Read-only: download reports + view own history. Cannot create jobs. |

### Live job logs
- Each job streams progress lines (discovery, per-file reading, periodic row counts,
  completion) to a **live console** in the UI (`GET /jobs/{id}/logs?after_id=N`,
  polled). Lets you verify exactly which files were scanned and watch progress in
  real time.

### User management
- Admins can **create, update (role / active / name / password), and delete** users.
  Delete is blocked (409) for users with related records — deactivate them instead.

### Operational CLIs (in the api container)
| Command | Purpose |
|---------|---------|
| `python -m app.scripts.seed` | Seed roles/permissions, first admin, demo shortcodes |
| `python -m app.scripts.s3_check --from --to` | Verify S3 connectivity + which daily files exist in a range |
| `python -m app.scripts.s3_peek --date` | Peek a CSV header (read-only Range GET) |
| `python -m app.scripts.extract_check --shortcodes --from --to` | Run the extractor against real data, print stats |
| `python -m app.scripts.job_run --user --shortcodes --from --to` | Run a full job (extract→zip→store) for a user |
| `python -m app.scripts.shortcode_add --code --name [--grant email]` | Register a shortcode (+ optional grant) |

---

### Email delivery (Phase 8)
- Send a completed report by email. Primary provider is **Gmail via OAuth2** (refresh
  token → access token → Gmail API); **SMTP** also supported. All config from `.env`.
- **Small** reports (≤ `EMAIL_MAX_ATTACHMENT_BYTES`) are sent as a **ZIP attachment**;
  **large** reports as a **short-lived secure download link** (reuses the signed
  download token).
- Runs on the Celery `email` path; delivery is tracked (`email_deliveries`: recipient,
  method, status PENDING/SENT/FAILED, error, timestamps) and audit-logged.
- Recipient defaults to the requester. UI: **Email report** button on the job page +
  a delivery-status list.

## 🔜 Planned

### Security hardening (Phase 9)
- Run worker/api as a non-root user; review auth/RBAC/logging; input validation;
  production HTTPS guidance; rate-limit review; secret handling review.

### AI / n8n integration (Phase 10)
- Scoped `/internal` API for the external n8n VM (create job, check status, get
  metadata, get download link, request email). No direct S3 access for AI/n8n.
- Natural-language → extraction parameters workflow (documentation + API only).

### Nice-to-haves (backlog)
- Admin UI for **update user / update shortcode / revoke grant** (APIs already exist).
- Sub-day timezone handling configuration (current comparisons are naive/local).
- Recovery of malformed rows (currently ~0.15% of rows with an unquoted newline are
  skipped and counted).
- Optional per-shortcode S3 prefix overrides surfaced in the UI.

---

## Behaviour notes

- **"0 records / files missing":** if a job completes with `files_processed = 0` and
  a non-zero `missing` count, the daily files for that date range were **not found in
  S3** — the extractor never opened any file (`rows_scanned = 0`). This is expected
  when the data doesn't exist for those dates. Verify coverage with
  `python -m app.scripts.s3_check --from <d> --to <d>`.
- **Shortcodes must be registered** before anyone (including admins) can extract them.
  Register via the admin **Shortcodes** screen or `shortcode_add` CLI.
- **Downloads are authorization-checked** and streamed from local storage; non-owners
  get 404, expired reports 410.
