# Deployment & Operations

Detailed runbook. The quickstart (deploy-from-scratch + redeploy) is in the root
[README](../README.md); this covers verification, the operational CLIs, backups,
scaling, troubleshooting, optional TLS for an IP, and local development.

Target: a Linux server running **Docker + Docker Compose**, reachable at a **local IP**
over **HTTP** on port **80**. Every value comes from `.env` — see
[env-reference.md](env-reference.md).

---

## 1. Prerequisites

- Docker Engine + Compose plugin (`curl -fsSL https://get.docker.com | sh`).
- Port **80** open on the server (`sudo ufw allow 80/tcp` if `ufw` is active).
- Network egress to **AWS S3** and (for email) to Google APIs.
- AWS credentials with **read-only** S3 access (or an attached IAM role).

---

## 2. First-time deploy

See the [README](../README.md) §2 for the exact steps. In short:

```bash
git clone <repo-url> && cd Client-Data-Extraction-from-S3
cp backend/.env.example backend/.env      # edit — see env-reference.md
cp deploy/.env.example  deploy/.env       # edit — Postgres creds + NEXT_PUBLIC_API_BASE_URL
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml exec api python -m app.scripts.seed
```

Migrations run automatically when `api` starts. The bundled Postgres auto-creates the
DB/user from `deploy/.env` on first start (only on first start — see
[env-reference.md](env-reference.md#database) if you change creds later).

### Verify

```bash
curl -fsS http://<SERVER_IP>/api/v1/health    # {"status":"ok"}
curl -sS  http://<SERVER_IP>/api/v1/ready       # {"status":"ready","checks":{db,redis,s3}}
```
Then open `http://<SERVER_IP>` and sign in with the seeded admin.

---

## 3. Operational CLIs (run inside the api container)

```bash
DC="docker compose -f deploy/docker-compose.prod.yml exec api"

# Seed roles/permissions, first admin, demo shortcodes (idempotent)
$DC python -m app.scripts.seed

# Verify S3 + see which daily files exist in a range (incl. multi-part)
$DC python -m app.scripts.s3_check --from 2026-08-01 --to 2026-08-02

# Peek a CSV header (read-only, first ~64 KB)
$DC python -m app.scripts.s3_peek --date 2026-08-01

# Register a shortcode (+ optionally grant a user)
$DC python -m app.scripts.shortcode_add --code 8890 --name "Client 8890" --grant analyst@x.com

# Dry-run the extractor against real data (prints counts, no job record)
$DC python -m app.scripts.extract_check --shortcodes 8890 --from 2026-08-01 --to 2026-08-01

# Run a full job for a user (extract → zip → store)
$DC python -m app.scripts.job_run --user admin@x.com --shortcodes 8890 --from 2026-08-01 --to 2026-08-01
```

(Day-to-day, shortcodes/users are managed in the web UI under **Admin**; the CLIs are
for setup and diagnostics.)

---

## 4. Redeployment

| Change | Command |
|--------|---------|
| Code (pull new) | `git pull && docker compose -f deploy/docker-compose.prod.yml up -d --build` (migrations auto-run) |
| `502` right after a rebuild | `docker compose -f deploy/docker-compose.prod.yml restart nginx` (nginx re-resolves new containers) |
| `backend/.env` only | `docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api worker beat` |
| `NEXT_PUBLIC_*` in `deploy/.env` | `… build frontend && … up -d frontend` (baked in at build time) |
| Rollback | `git checkout <tag> && … up -d --build` |

Prefer forward fixes over DB downgrades; keep migrations backward-compatible. Local
report artifacts are regenerable — a rollback never risks the S3 source (read-only).

---

## 5. Backups, scaling, operations

- **Backup Postgres** regularly:
  ```bash
  docker compose -f deploy/docker-compose.prod.yml exec db \
    pg_dump -U <POSTGRES_USER> <POSTGRES_DB> > backup_$(date +%F).sql
  ```
  Report artifacts are regenerable from S3, so backing them up is optional.
- **Scale workers:** `… up -d --scale worker=3` (shared `report_storage` volume).
- **Exactly one `beat`** — never scale it above 1.
- **Logs:** `… logs -f <service>`. **Metrics to watch:** queue depth, job `FAILED`
  rate, `login.failure`/`authz.deny` spikes, storage disk usage.

---

## 6. Optional: encrypt traffic on the IP (self-signed TLS)

Plain HTTP is fine on a trusted internal network. To encrypt anyway (login tokens
travel over it), use a **self-signed cert for the IP**:

```bash
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out    deploy/nginx/certs/fullchain.pem \
  -subj "/CN=<SERVER_IP>" -addext "subjectAltName=IP:<SERVER_IP>"
```
Then in `deploy/docker-compose.prod.yml`, mount `app.conf` (TLS) instead of
`app.http-only.conf` and the `certs` dir, set `NEXT_PUBLIC_API_BASE_URL` /
`BACKEND_CORS_ORIGINS` to `https://<SERVER_IP>`, and rebuild. Browsers show a one-time
"not trusted" warning (expected for self-signed).

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/ready` → `database error` | Wrong `DATABASE_URL` / creds mismatch / unencoded `@` in password | Match `backend/.env` to `deploy/.env`, host `db`, encode `@`→`%40` |
| `/ready` → `redis error` | Redis host wrong | `REDIS_URL=redis://redis:6379/0` (service name, not `localhost`) |
| `/ready` → `s3 error` | Wrong region/creds or endpoint set to a stray value | Check `AWS_*`, `S3_BUCKET`; `S3_ENDPOINT_URL` must be empty or a URL |
| api exits: "Missing required environment configuration" | `JWT_SECRET`/`DATABASE_URL`/`REDIS_URL` blank | Fill `backend/.env` |
| `502 Bad Gateway` (api is Up) | nginx cached an old container IP after a rebuild | `… restart nginx` |
| Job scanned only 1 file for a day | (fixed) | Ensure code is up to date — multi-part discovery is supported |
| Email `FAILED` with 403 scopes | Gmail token missing `drive.file` scope | Re-consent, see [gmail-drive-setup.md](gmail-drive-setup.md) |
| A blank field shows `# …` as its value | Inline comment after an empty value in `.env` | Remove inline comments; put comments on their own line |

---

## 8. Local development (without Docker)

Requires Python 3.11+ and a reachable Postgres + Redis (or SQLite for early testing).

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate     # Windows; use bin/activate on Linux
pip install -e ".[dev,postgres]"
cp .env.example .env                                  # edit
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# separate processes:
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
celery -A app.workers.celery_app.celery_app beat --loglevel=INFO

# tests
python -m pytest            # or a single file: python -m pytest tests/test_s3.py
```

Frontend (needs Node 20+):
```bash
cd frontend && npm install
cp .env.local.example .env.local     # edit NEXT_PUBLIC_API_BASE_URL
npm run dev                          # http://localhost:3000
```
