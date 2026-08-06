# Environment Reference — how to obtain every value

Two env files (both gitignored):

| File | Purpose | Template |
|------|---------|----------|
| `backend/.env` | Application runtime config | `backend/.env.example` |
| `deploy/.env` | Compose infra: Postgres creds, frontend build args | `deploy/.env.example` |

> **Golden rule:** nothing is hardcoded — every value is read from these files.
> **No inline comments after a value** (`KEY=value  # note`) — some parsers keep the
> `# note` as the value. Put comments on their own line.

---

## App (`backend/.env`)

| Key | What / how |
|-----|-----------|
| `APP_ENV` | `production` on the server. |
| `API_V1_PREFIX` | Keep `/api/v1`. |
| `BACKEND_CORS_ORIGINS` | The site origin the browser uses: `http://<SERVER_IP>`. |
| `LOG_LEVEL` | `INFO` (or `DEBUG` when troubleshooting). |
| `ENABLE_API_DOCS` | `true` (default). Set `false` to hide `/docs` in production. |

## Auth (`backend/.env`)

| Key | What / how |
|-----|-----------|
| `JWT_SECRET` ⭐ | Long random string: `openssl rand -hex 48`. Rotating it logs everyone out. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes (defaults fine). |
| `PASSWORD_HASH_SCHEME` | `argon2`. |
| `LOGIN_RATE_LIMIT_*` | Login throttle (defaults fine). |
| `COOKIE_SECURE` | `false` over HTTP/IP (else the refresh cookie won't be sent). `true` with TLS. |
| `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` | Used by `python -m app.scripts.seed` to create the first admin. |
| `SEED_DEMO_DATA` | `true` also seeds demo shortcodes `8990`, `1234`. |

## Database

`DATABASE_URL` ⭐ — SQLAlchemy URL for Postgres:
```
postgresql+psycopg://USER:PASSWORD@db:5432/DBNAME
```
- Host is **`db`** (the compose service). `USER`/`PASSWORD`/`DBNAME` must equal
  `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` in `deploy/.env`.
- **URL-encode special chars in the password** — e.g. `@` → `%40`
  (`Zaryab@2026` → `Zaryab%402026`).
- ⚠️ The bundled Postgres applies `POSTGRES_*` **only on first start** (empty
  `db_data` volume). If you change creds later, reset the volume:
  `docker compose … down && docker volume rm deploy_db_data && … up -d --build`.

## Redis / Celery (`backend/.env`)

| Key | Value |
|-----|-------|
| `REDIS_URL` ⭐ | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` |
| `CELERY_TASK_TIME_LIMIT` | Generous (default 21600 = 6h) for large multi-day scans. |
| `RETENTION_CLEANUP_INTERVAL_SECONDS` | How often beat runs cleanup (default daily). |

## AWS / S3 (`backend/.env`) — read-only source

| Key | What / how |
|-----|-----------|
| `AWS_REGION` | Bucket's region (S3 console → bucket → Properties), e.g. `me-central-1`. |
| `S3_BUCKET` | e.g. `bk-kannel`. |
| `S3_PREFIX` | Folder of daily files, e.g. `daily-jasminfiles-fatib`. |
| `S3_FILE_TEMPLATE` | `daily-data_{yyyy}-{mm}-{dd}.csv`. |
| `S3_DISCOVERY_MODE` | `list` (whole-prefix) or `template` (per-day targeted). Both find multi-part files. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM user access keys, **or** leave blank to use an attached IAM role. Scope the IAM policy to `s3:GetObject` + `s3:ListBucket` on the bucket (policy in [security-review.md](security-review.md)). |
| `S3_ENDPOINT_URL` | Leave **empty** for real AWS. Only for S3-compatible stores. |

Validate with `python -m app.scripts.s3_check --from … --to …`.

## CSV extraction (`backend/.env`) — confirm against a real header

| Key | Value (for the Jasmin export) |
|-----|-------|
| `CSV_SHORTCODE_COLUMN` | `source_addr` (numeric sender IDs like `8890`). |
| `CSV_DESTINATION_COLUMN` | `destination_addr` (optional filter). |
| `CSV_DELIMITER` | `,` |
| `CSV_HAS_HEADER` | `true` |
| `CSV_COMPRESSION` | `none` (or `gzip` if files are compressed). |
| `CSV_TIMESTAMP_COLUMN` | `created_at` |
| `CSV_TIMESTAMP_FORMAT` | `%Y-%m-%d %H:%M:%S.%f` |

Inspect a real header with `python -m app.scripts.s3_peek --date YYYY-MM-DD`.

## Jobs / storage / retention (`backend/.env`)

| Key | Value |
|-----|-------|
| `JOB_ID_STRATEGY` | `ext_seq` → `EXT-YYYYMMDD-NNNNNN` (or `uuid4`). |
| `MAX_RANGE_DAYS` | Max width of a single extraction (default 92). |
| `REPORT_STORAGE_PATH` | `./storage` (mapped to the shared volume). |
| `REPORT_RETENTION_DAYS` | Auto-delete reports after N days (0 = keep forever). |
| `ZIP_COMPRESSION_LEVEL` | 0–9 (default 6). |

## Email — Gmail (`backend/.env`)

See the step-by-step in [gmail-drive-setup.md](gmail-drive-setup.md).

| Key | What / how |
|-----|-----------|
| `EMAIL_ENABLED` | `true` to enable emailing reports. |
| `EMAIL_PROVIDER` | `gmail`. |
| `EMAIL_MAX_ATTACHMENT_BYTES` | Reports at/under this size are attached; larger → Google Drive link. `0` = always Drive. |
| `PUBLIC_API_BASE_URL` | `http://<SERVER_IP>/api/v1` (used only for in-app links). |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` | From your Google Cloud OAuth client. |
| `GMAIL_REFRESH_TOKEN` | OAuth refresh token with **`gmail.send` + `drive.file`** scopes. |
| `GMAIL_TOKEN_URI` | `https://oauth2.googleapis.com/token`. |
| `GMAIL_SENDER` | The "from" address, e.g. `zaryab.ansari@eocean.net`. |
| `GDRIVE_FOLDER_ID` | Optional Drive folder for large reports (else My Drive root). |

---

## Compose-level (`deploy/.env`)

| Key | What / how |
|-----|-----------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Credentials for the bundled Postgres. Must match `DATABASE_URL` (host `db`). |
| `API_WORKERS` / `CELERY_WORKER_CONCURRENCY` | Process/thread counts — scale to the CPU. |
| `NEXT_PUBLIC_API_BASE_URL` | Browser's API URL: `http://<SERVER_IP>/api/v1`. **Baked in at build time** — change → rebuild frontend. |
| `NEXT_PUBLIC_MAX_RANGE_DAYS` / `NEXT_PUBLIC_JOB_POLL_INTERVAL_MS` / `NEXT_PUBLIC_IDLE_TIMEOUT_MIN` | UI behavior (defaults 92 / 3000 / 15). |
| `NEXT_PUBLIC_ENABLE_ASSISTANT` | Feature flag for the (Phase 10) AI assistant. |

---

## Quick checklist

- [ ] `JWT_SECRET` generated
- [ ] `POSTGRES_*` in `deploy/.env`; `DATABASE_URL` matches (host `db`, `@`→`%40`)
- [ ] `REDIS_URL` / Celery URLs use host `redis`
- [ ] `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` = your server IP
- [ ] AWS read-only creds/role + `AWS_REGION`, `S3_BUCKET`, `S3_PREFIX`
- [ ] CSV columns confirmed from a real header
- [ ] (Email) Gmail OAuth with `gmail.send` + `drive.file`, `EMAIL_ENABLED=true`
- [ ] No inline comments after values
