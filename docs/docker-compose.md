# Docker Compose — Containers & What They Do

Production stack is defined in `deploy/docker-compose.prod.yml`. `docker compose … up -d
--build` starts seven services. Configuration comes from two files:

- **`deploy/.env`** — infrastructure vars used by the compose file itself (Postgres
  credentials, frontend build args, worker counts).
- **`backend/.env`** — the application's runtime config (loaded into `api`/`worker`/`beat`
  via `env_file`).

---

## Services

| Service | Image / build | Purpose | Ports | Notes |
|---------|---------------|---------|-------|-------|
| **nginx** | `nginx:1.27` | Reverse proxy. `/` → frontend, `/api/` → api. | **80** (and 443 if you enable TLS) | Config mounted from `deploy/nginx/app.http-only.conf`. Re-resolves upstreams via Docker DNS. |
| **frontend** | build `../frontend` | Next.js web app (standalone build). | 3000 (internal) | `NEXT_PUBLIC_*` are **baked in at build time** from `deploy/.env` — change them → rebuild. |
| **api** | build `../backend` | FastAPI. Runs `alembic upgrade head` then `uvicorn`. | 8000 (internal) | Migrations auto-run on start. Shares the `report_storage` volume. |
| **worker** | build `../backend` | Celery worker — runs extraction + email tasks. | — | Streams S3, writes reports to the shared volume. Scale with `--scale worker=N`. |
| **beat** | build `../backend` | Celery beat — schedules retention cleanup. | — | Run **exactly one** instance. |
| **db** | `postgres:16` | Application metadata database. | 5432 (internal) | Auto-creates the DB/user from `deploy/.env` on first start. Data in the `db_data` volume. |
| **redis** | `redis:7` | Celery broker/result backend + rate-limit/denylist. | 6379 (internal) | — |

Only **nginx** publishes a host port (80). Everything else talks over the internal
compose network by service name (`db`, `redis`, `api`, `frontend`).

---

## How they connect

```
nginx ──/──▶ frontend:3000
      ──/api/─▶ api:8000
api ──▶ db:5432        (metadata)
api ──▶ redis:6379     (enqueue jobs, rate-limit)
worker/beat ──▶ redis  (consume jobs / schedule)
worker ──▶ db          (update job status, write report metadata, job logs)
worker ──▶ AWS S3       (read-only stream of source CSVs)
api + worker ──▶ report_storage volume  (generated CSV/ZIP/metadata)
```

The **`report_storage` volume is shared by `api` and `worker`**: the worker writes the
report, the api serves the download. (On a single host this "just works"; if you ever
run api/worker on separate machines, this must become a shared filesystem.)

---

## Volumes

| Volume | Mounted at | Holds |
|--------|-----------|-------|
| `db_data` | `db:/var/lib/postgresql/data` | Postgres data (persist across restarts). |
| `report_storage` | `api` and `worker` `:/app/storage` | Generated reports: `storage/jobs/<job_id>/`. |

---

## Common operations

```bash
# start / rebuild everything
docker compose -f deploy/docker-compose.prod.yml up -d --build

# status
docker compose -f deploy/docker-compose.prod.yml ps

# logs (follow)
docker compose -f deploy/docker-compose.prod.yml logs -f api
docker compose -f deploy/docker-compose.prod.yml logs -f worker

# reload backend/.env (no rebuild)
docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api worker beat

# run a one-off command in the api container
docker compose -f deploy/docker-compose.prod.yml exec api python -m app.scripts.seed

# scale workers
docker compose -f deploy/docker-compose.prod.yml up -d --scale worker=3
```

More: [deployment.md](deployment.md).
