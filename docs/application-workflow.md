# Application Working Flow — Client Data Extraction & Delivery System

This is the single source-of-truth document for how the system works. More focused
documents can be added to `docs/` later if needed.

---

## 1. What the system does (in one paragraph)

An authenticated user selects one or more **shortcodes** (e.g. `8990`) and a
**date/time range**. The backend finds the **daily CSV files in AWS S3 that fall in
that date range**, streams through **each** file, and **extracts only the rows whose
`source_addr` column matches a selected shortcode**. The matching rows from all files
are combined into a single CSV, packaged into a ZIP with a metadata file, assigned a
unique Job ID, stored in local application storage, and made available to the user to
**download** or **receive by email**.

> **Key correction to the model:** the shortcode is a **value inside the CSV** (the
> `source_addr` column), **not** a folder/prefix. The date range decides *which files*
> to open; `source_addr == shortcode` decides *which rows* to keep.

---

## 2. Critical constraint: very large files

Source files are **large** — a single selected range can be, for example, **~10 files
of ~1 GB each (~10 GB scanned)**. Everything about processing is designed around this:

- **Never load a whole file into memory.** Files are streamed from S3 and parsed
  **row by row**; matching rows are appended to an on-disk output file. Memory stays
  flat regardless of file size.
- **Jobs are long-running and asynchronous.** Extraction runs in a **Celery background
  worker**, never inside the HTTP request. The API returns a Job ID immediately; the
  user tracks progress and downloads when ready.
- **Progress is reported**, so a 10 GB scan shows "file 4 of 10, 3.2 GB read, 812
  rows matched" rather than an opaque spinner.
- **Per-file parallelism (optional).** Because files are independent, each file can be
  processed as its own subtask across multiple workers, then results merged — cutting
  wall-clock time roughly by the number of workers. Enabled/disabled via config.
- **Generous, configurable timeouts.** Task soft/hard time limits are set high enough
  for multi-GB scans and come from `.env`.
- **Cancelable.** A running job can be cancelled; partial work is discarded cleanly.

---

## 3. The core extraction logic

```
Inputs:  shortcodes = ["8990"]           (matched against the source_addr column)
         date_from, date_to              (selects which daily files to scan)

1. Discover files:
     List the daily CSV files in S3 (configured bucket/prefix) whose date falls
     within [date_from .. date_to].  → e.g. 10 files.

2. For each file (streamed, never fully loaded):
     open a streaming read of the S3 object
     read the header row → locate the source_addr column (name from .env, default
       "source_addr")
     for each subsequent row:
         if row[source_addr] in selected shortcodes:
             (optional) if a timestamp column is configured and the range is sub-day,
                 also require the row timestamp ∈ [date_from .. date_to]
             append the row to the combined output CSV
     track: bytes_read, rows_scanned, rows_matched, per-file errors

3. Combine:
     one header written once + all matched rows from all files = report.csv

4. Package & store:
     build metadata.json + report.zip  (report.csv + metadata.json)
     store under a unique Job ID in local application storage

5. Deliver:
     user downloads the ZIP, or receives it by email (attachment or secure link)
```

**Configurable, not hardcoded** (`.env`):
- `CSV_SHORTCODE_COLUMN=source_addr` — the column the shortcode is matched against.
- `CSV_DELIMITER`, `CSV_HAS_HEADER`, and (if used) `CSV_TIMESTAMP_COLUMN` /
  `CSV_TIMESTAMP_FORMAT` for optional in-file time filtering.
- File format can vary; column names are all read from config, so the code is not
  tied to one client's exact layout.

---

## 4. S3 file discovery (which files are in range)

- The daily files live under a configured bucket + prefix (from `.env`). The observed
  example was `s3://bk-kannel/daily-jasminfiles-fatib/daily-data_2023-09-01.csv`, so
  files are **one per day** and the date is in the filename.
- Two discovery modes (config `S3_DISCOVERY_MODE`):
  1. **`template`** — build exact keys from a filename template + each date in range.
  2. **`list`** — `ListObjectsV2` under the prefix and parse the date out of each
     filename, keeping those in range (robust to naming drift / extra suffixes).
- **S3 is strictly read-only:** the code has no write/delete paths and the IAM
  credentials are read-only. Source files are never modified or deleted.
- A missing day in the range is a **warning** recorded in metadata (job completes as
  `PARTIAL`), unless strict mode is enabled.

---

## 5. End-to-end flow (all components)

```
User (Next.js)
  │  login (JWT)
  │  GET /shortcodes            → only shortcodes the user is authorized for
  │  POST /jobs {shortcodes, date_from, date_to, delivery}
  ▼
FastAPI
  │  authenticate + authorize (RBAC + shortcode permission)
  │  validate range → create Job (QUEUED) → enqueue on Redis → return {job_id} (202)
  ▼
Celery worker  (long-running, streaming)
  │  status=RUNNING
  │  discover in-range S3 files
  │  stream each file → filter rows where source_addr ∈ shortcodes → append to CSV
  │  update progress (files_done, bytes_read, rows_matched)
  │  build ZIP + metadata.json → atomic move into {job_id}/ folder
  │  status=SUCCESS (or PARTIAL) → optionally enqueue email
  ▼
User
  │  polls GET /jobs/{job_id} → sees progress → SUCCESS
  │  GET /reports/{job_id}/download   (authz-checked stream of the ZIP)
  └  or receives email (small: attachment · large: short-lived signed link)
```

---

## 6. Components & responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Next.js frontend** | Login, dashboard, shortcode + date/time selection, job status, download, email, history, optional AI assistant |
| **FastAPI** | Auth, RBAC + shortcode permissions, REST APIs, job intake, download streaming — stays thin, never does the heavy scan |
| **Redis** | Celery broker/queue + rate-limit counters + token denylist |
| **Celery worker** | The long-running streaming extraction; email send; retention |
| **Celery beat** | Schedules retention cleanup |
| **AWS S3** | Read-only source of truth for the large daily CSV files |
| **Local storage** | Holds generated CSV/ZIP/metadata per Job ID (configurable path, retention) |
| **PostgreSQL** | Application **metadata only** — never client CSV data |
| **AWS SES / SMTP** | Email delivery (attachment vs. secure link by size) |
| **n8n (external)** | Automation on 192.168.255.170 — integrates via a scoped API only; **never** direct S3 access. We do not deploy n8n. |

---

## 7. Jobs, storage & delivery

- **Job ID:** unique, non-enumerable (ULID/UUID). Used in URLs, the storage folder,
  logs, and audit entries.
- **Local storage layout:** `{REPORT_STORAGE_PATH}/{job_id}/` containing
  `report.csv`, `report.zip`, `metadata.json`. Artifacts are written to a temp dir and
  **atomically moved** into place so a download never sees a half-written file.
- **metadata.json** records shortcodes, date range, source files scanned, missing
  files, rows scanned/matched, ZIP size, SHA-256 checksum, and expiry.
- **Retention:** artifacts expire after `REPORT_RETENTION_DAYS` and are deleted by a
  scheduled job; the S3 source is never touched.
- **Download:** the server resolves the path from the DB, checks ownership/permission,
  and streams the ZIP — the client never supplies or sees a filesystem path.
- **Email:** small reports attach the ZIP; large reports (over
  `EMAIL_MAX_ATTACHMENT_BYTES`) send a **short-lived signed download link** instead.

---

## 8. Security & access control (summary)

- **Authentication:** JWT (short-lived access + rotating refresh); passwords hashed
  (argon2/bcrypt); login rate-limited.
- **Authorization (two layers, server-side, deny-by-default):**
  1. **RBAC** — role → permissions (admin / analyst / viewer).
  2. **Shortcode-level** — a user may only extract shortcodes explicitly granted to
     them; `GET /shortcodes` returns only those, and `POST /jobs` re-validates every
     requested shortcode.
- **S3 read-only** enforced in code and IAM.
- **No client CSV data in the DB.**
- **n8n / AI** get a scoped token with their own shortcode grants and **no S3
  credentials**; large deliveries use signed short-lived links.
- **Audit logs** for logins, job creation, downloads, emails, permission changes, and
  denied attempts.

---

## 9. Configuration rule

Every configurable value comes from `.env` — nothing hardcoded: secrets, credentials,
AWS/S3 config and bucket names, DB URL, Redis URL, JWT secret, email settings, local
storage paths, retention settings, n8n URL, API keys, environment IPs/URLs.
`.env.example` is committed (with blanks); the real `.env` is gitignored.

Key extraction-related settings:

```ini
S3_BUCKET=bk-kannel
S3_PREFIX=daily-jasminfiles-fatib          # folder of daily files to scan
S3_FILE_TEMPLATE=daily-data_{yyyy}-{mm}-{dd}.csv
S3_DISCOVERY_MODE=list                      # list | template
CSV_SHORTCODE_COLUMN=source_addr            # shortcode is matched against THIS column
CSV_DELIMITER=,
CSV_HAS_HEADER=true
CSV_TIMESTAMP_COLUMN=                        # optional, for sub-day time filtering
CSV_TIMESTAMP_FORMAT=
EXTRACTION_PARALLEL_FILES=true              # process files concurrently across workers
CELERY_TASK_TIME_LIMIT=21600                # generous limit for multi-GB scans
REPORT_STORAGE_PATH=./storage
REPORT_RETENTION_DAYS=30
```

---

## 10. Performance notes for large scans

- Stream from S3 (`get_object` streaming body); parse incrementally; write matches to
  disk immediately.
- If source files are gzip-compressed, decompress on the fly while streaming (config
  `CSV_COMPRESSION=gzip|none`).
- Optionally read S3 objects in byte ranges to parallelize a single huge file (advanced;
  off by default — per-file parallelism across the 10 files is usually enough).
- Keep the combined output on disk; only the final ZIP is loaded for checksum/size,
  and even that is streamed.
- Report progress frequently so long jobs are observable; make jobs cancelable.

---

## 11. Build order (phases)

1. Foundation (config from `.env`, DB + migrations, health checks, compose).
2. Auth + RBAC.
3. Shortcodes + shortcode-level permissions.
4. **S3 discovery + streaming `source_addr` extraction** (the core, tested on large
   fixtures for constant memory).
5. Jobs + Celery (async, progress, cancel, idempotent/atomic).
6. Local storage + ZIP + download.
7. Email (attachment vs. signed link).
8. Retention.
9. Frontend.
10. n8n integration (scoped API).
11. Optional AI assistant.
12. Hardening + deployment.

Deployment/redeployment steps (install, code redeploy, config-only redeploy,
rollback, scaling workers, monitoring) will be documented alongside the compose files
when implementation begins.

---

## Still needed before Phase 4

A **real header row** from one of the daily CSV files, to confirm:
- the exact `source_addr` column name (default assumed `source_addr`),
- the delimiter,
- whether files are plain or gzip-compressed,
- and, if sub-day time ranges are needed, the timestamp column name/format.

This only sets `.env` defaults — the design does not change.
