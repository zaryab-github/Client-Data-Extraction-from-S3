# Client Data Extraction & Delivery System

A production-ready system that lets authenticated users select authorized
**shortcodes** and a **date/time range**, then scans the large daily CSV files in
**AWS S3** that fall in that range, **extracts only the rows whose `source_addr`
matches a selected shortcode** (e.g. `8990`), packages them into a **ZIP** (with
metadata), and lets the user **download** or **email** the result — with full RBAC,
shortcode-level permissions, and audit logging.

- **Extraction model:** the shortcode is a **value inside the CSV** (`source_addr`
  column); the date range selects which files to scan, `source_addr == shortcode`
  selects which rows to keep.
- **Large files:** files can be ~1 GB each (10+ per range). Extraction streams row by
  row in a **Celery background worker** — never loading whole files into memory.
- **Source of truth:** AWS S3 (`bk-kannel`), treated as **read-only**.
- **Database:** application **metadata only** — never client CSV data.
- **Async processing:** FastAPI + Celery + Redis.
- **Automation:** external n8n integrates via a **scoped, permissioned API** — never
  direct S3 access.
- **Configuration:** everything comes from `.env`. Nothing sensitive is hardcoded.

---

## Status

**Phases 1–7 implemented and deployed** (auth, RBAC, S3 integration, streaming
extraction, job storage, async Celery jobs, web dashboard + admin). Phases 8–10
(email, hardening, n8n) are planned. See
[docs/features.md](docs/features.md) for the full feature catalogue and roadmap.

## Documentation

- **[docs/features.md](docs/features.md)** — what's built, what's planned, and the
  operational CLIs (the "living" feature/roadmap doc).
- **[docs/application-workflow.md](docs/application-workflow.md)** — end-to-end design
  and the extraction model.
- **[deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md)** — deploy/redeploy runbook (nginx,
  Docker Compose, IP-based setup).
- **[deploy/ENV_REFERENCE.md](deploy/ENV_REFERENCE.md)** — how to obtain every `.env`
  value.
- **[development_phases.md](development_phases.md)** — the phase-by-phase plan.

## Tech stack

- **Backend:** Python, FastAPI, Celery, SQLAlchemy/Alembic
- **Queue/broker:** Redis
- **Database:** PostgreSQL (metadata only)
- **Storage:** AWS S3 (read-only source) + local application storage (generated reports)
- **Email:** AWS SES or SMTP
- **Frontend:** Next.js (React, TypeScript)
- **Automation:** external n8n (not deployed here) via scoped API

## Quickstart (after implementation)

See [docs/19-deployment.md](docs/19-deployment.md). In brief:

```bash
cp backend/.env.example backend/.env      # then edit
cp frontend/.env.local.example frontend/.env.local
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml exec api alembic upgrade head
```

## License

Proprietary — internal use.
