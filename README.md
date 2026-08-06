# Client Data Extraction & Delivery System

Authenticated users select authorized **shortcodes** and a **date/time range**; the
system streams the matching rows out of the large daily CSV files in **AWS S3**
(filtering on `source_addr`, optionally `destination_addr`), packages them into a ZIP,
and delivers it by **download** or **email** (Gmail — attachment for small reports, a
Google Drive link for large ones).

Runs entirely on a **local IP over HTTP** behind nginx. S3 is read-only; the database
holds application **metadata only** (never client CSV data).

> Full documentation is in **[`docs/`](docs/README.md)** — architecture, per-`.env`
> reference, Gmail/Drive setup, container guide, security review, and phases.

---

## 1. Architecture flow

```
                               Browser  (http://<SERVER_IP>)
                                    │
                                    ▼
                            ┌───────────────┐
                            │   nginx  :80  │   reverse proxy
                            └──────┬────────┘
                     ┌─────────────┴──────────────┐
              /  →   ▼                      /api/  ▼
                ┌──────────────┐            ┌──────────────────┐
                │  frontend    │            │  api (FastAPI)   │
                │ Next.js :3000│            │      :8000       │
                └──────────────┘            └───────┬──────────┘
                       auth · RBAC · shortcode authz │  create job + enqueue
                    ┌─────────────────┬──────────────┼───────────────┐
                    ▼                 ▼              ▼                │
              ┌───────────┐    ┌────────────┐  ┌──────────────┐      │
              │ Postgres  │    │   Redis    │  │   AWS S3     │      │
              │ metadata  │    │  broker    │  │ (read-only)  │      │
              └───────────┘    └─────┬──────┘  └──────┬───────┘      │
                                     │ task           │ stream rows  │
                              ┌──────▼───────┐        │              │
                              │ Celery worker│◀───────┘              │
                              │  + beat      │  extract → filter      │
                              └──────┬───────┘  → CSV → ZIP → meta    │
                                     │ writes                         │
                              ┌──────▼─────────────┐                  │
                              │  local storage     │  jobs/<job_id>/  │
                              │  CSV + ZIP + meta   │                  │
                              └───┬────────────┬───┘                  │
                        download  ▼            ▼  email (Gmail)        │
                          (streamed ZIP)   small → attachment         │
                                           large → Google Drive link  │
   status + live logs  ◀──────────────────────────────────────────────┘
```

**Data flow:** login → select shortcodes + date/time → API validates auth + RBAC +
shortcode grants → creates a Job ID (`EXT-YYYYMMDD-NNNNNN`) → enqueues to Celery →
worker streams the in-range daily S3 files (multi-part aware), keeps rows matching the
shortcode(s) and time window → writes combined CSV + ZIP + `metadata.json` to local
storage → user downloads the ZIP or emails it. See
[docs/architecture.md](docs/architecture.md) for the full design.

---

## 2. Deployment from scratch

On a Linux server with **Docker + Docker Compose**, port **80** open.

```bash
# 1. Get the code
git clone <your-repo-url> Client-Data-Extraction-from-S3
cd Client-Data-Extraction-from-S3

# 2. Create the two env files (never committed)
cp backend/.env.example backend/.env
cp deploy/.env.example  deploy/.env
```

Edit the values (full guide: **[docs/env-reference.md](docs/env-reference.md)**).
Minimum to boot:

- **`deploy/.env`** — `POSTGRES_USER/PASSWORD/DB`, and `NEXT_PUBLIC_API_BASE_URL=http://<SERVER_IP>/api/v1`
- **`backend/.env`** — `JWT_SECRET` (`openssl rand -hex 48`), `DATABASE_URL=postgresql+psycopg://<user>:<pass>@db:5432/<db>` (URL-encode `@`→`%40`), `REDIS_URL=redis://redis:6379/0`, `CELERY_BROKER_URL=redis://redis:6379/1`, `CELERY_RESULT_BACKEND=redis://redis:6379/2`, `BACKEND_CORS_ORIGINS=http://<SERVER_IP>`, plus AWS/S3 and (optional) Gmail — see the env reference.

> ⚠️ No inline comments after a value in `.env` — some parsers keep `# …` as the value.

```bash
# 3. Build and start everything (db, redis, api, worker, beat, frontend, nginx)
docker compose -f deploy/docker-compose.prod.yml up -d --build

# 4. Seed roles/permissions + the first admin (set FIRST_ADMIN_* in backend/.env first)
docker compose -f deploy/docker-compose.prod.yml exec api python -m app.scripts.seed

# 5. Verify
curl -fsS http://<SERVER_IP>/api/v1/health     # {"status":"ok"}
curl -sS  http://<SERVER_IP>/api/v1/ready        # database/redis/s3 ok
```

Open **`http://<SERVER_IP>`** and sign in. Database migrations run automatically when
the `api` container starts. Register client shortcodes and grant users under
**Admin → Shortcodes / Users**.

For AWS credentials, Gmail/Drive, and every field, see
[docs/env-reference.md](docs/env-reference.md) and
[docs/gmail-drive-setup.md](docs/gmail-drive-setup.md).

---

## 3. Redeployment (after a change)

**Code change** (pull new code — migrations auto-run on api start):
```bash
git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build
```
If a rebuild recreated the `api`/`frontend` containers and nginx returns `502`, reload
nginx once so it re-resolves them:
```bash
docker compose -f deploy/docker-compose.prod.yml restart nginx
```

**Backend config change only** (edited `backend/.env`) — recreate the app containers to
reload it (no rebuild):
```bash
docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api worker beat
```

**Frontend URL / build-arg change** (edited `NEXT_PUBLIC_*` in `deploy/.env`) — these are
baked in at build time, so rebuild the frontend:
```bash
docker compose -f deploy/docker-compose.prod.yml build frontend
docker compose -f deploy/docker-compose.prod.yml up -d frontend
```

**Rollback:**
```bash
git checkout <previous-tag> && docker compose -f deploy/docker-compose.prod.yml up -d --build
```

More detail (troubleshooting, backups, scaling, optional self-signed TLS for the IP):
**[docs/deployment.md](docs/deployment.md)**.
