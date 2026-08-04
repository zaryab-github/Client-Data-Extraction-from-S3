# Backend — Client Data Extraction & Delivery System

FastAPI + Celery backend. **Phase 1 (foundation) only** — configuration, DB/Redis/
Celery wiring, and health/readiness. No business logic yet.

## Requirements

- Python 3.11+
- (For real deploys) PostgreSQL + Redis. Local tests use SQLite and need no servers.

## Setup

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -e ".[dev,postgres]"

cp .env.example .env        # then edit — set JWT_SECRET, DATABASE_URL, REDIS_URL
```

All configuration is read from `.env`. Nothing is hardcoded. Required at startup:
`JWT_SECRET`, `DATABASE_URL`, `REDIS_URL` (and a Celery broker, which defaults to
`REDIS_URL`). The app fails fast if any are missing.

## Run

```bash
# API
uvicorn app.main:app --reload --port 8000

# Celery worker (idle in Phase 1 — no tasks yet)
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
```

Endpoints (Phase 1):

- `GET /`                     — service info
- `GET /api/v1/health`        — liveness (always OK if process is up)
- `GET /api/v1/ready`         — readiness (checks DB + Redis; 503 if degraded)
- `GET /docs`                 — OpenAPI UI

## Tests (lightweight foundation checks)

```bash
pip install ".[dev]"
python -m pytest
```

Verifies: environment config loads, DB config loads (SELECT 1 on SQLite), Redis
config loads, Celery config loads, and the FastAPI app starts and serves `/health`.
No live Postgres/Redis is required for the test run.

## Structure

```
app/
  config.py            # Pydantic Settings — all values from .env
  main.py              # FastAPI app factory
  api/routes/health.py # health + readiness
  db/                  # engine/session (from DATABASE_URL), declarative base
  core/redis.py        # Redis client (from REDIS_URL)
  core/logging.py      # logging config
  workers/celery_app.py# Celery app (broker/backend from .env)
  services/ schemas/ repositories/ db/models/   # placeholders for later phases
```
