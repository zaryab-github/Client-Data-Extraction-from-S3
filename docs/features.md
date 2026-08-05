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

### S3 source integration (Phase 3)
- Read-only discovery of the daily CSV files that fall in a date range.
- Two discovery modes (`list` / `template`), configurable via `.env`.
- Missing daily files are reported (not fatal). S3 is never modified or deleted.

### CSV extraction engine (Phase 4)
- Streams each daily file from S3 **row by row** (constant memory) — safe for the
  real 100–236 MB/day files.
- Keeps rows where the shortcode column (`source_addr`) matches **and** the timestamp
  column (`created_at`) is within range. Rows with a missing/unparseable timestamp are
  **kept** and counted.
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

### Web app + admin (Phase 7)
- **Dashboard** with stat tiles and recent jobs.
- **Extract** screen: authorized-shortcode multi-select + date/time range → Generate.
- **Job status** page: live polling with a status badge; **ZIP download**; clear
  "no source files found" notice when a range has no data.
- **History** with status filter and per-job download.
- **Admin** screens: register/list **shortcodes**, create/list **users** (+ roles),
  **grant** shortcode access, view **audit logs**.
- Modern tabbed UI, dark theme, colored status badges.

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

## 🔜 Planned

### Email delivery (Phase 8)
- Send a completed report by email via **AWS SES or SMTP** (from `.env`).
- Small reports as a **ZIP attachment**; large reports as a **short-lived secure
  download link**.
- Email delivery status + audit; recipient defaults to the requester.
- Enables the currently-disabled "Email report" button in the UI.

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
