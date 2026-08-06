# Operations & Troubleshooting Runbook

Hands-on commands for anyone operating the system: checking jobs, managing containers,
reading logs, working with the database, and fixing common problems.

All commands assume you're in the repo root. This shortcut is used throughout:

```bash
DC="docker compose -f deploy/docker-compose.prod.yml"
```

---

## 1. Check a job's status & details

### Via the API (curl)

```bash
# 1) Get a token (use a real user)
TOKEN=$(curl -s -X POST http://<SERVER_IP>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@x.com","password":"<password>"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2) List jobs (admins see all; others see their own)
curl -s http://<SERVER_IP>/api/v1/jobs -H "Authorization: Bearer $TOKEN"

# 3) One job's full detail (status, counts, report, files scanned)
curl -s http://<SERVER_IP>/api/v1/jobs/EXT-20260805-000010 -H "Authorization: Bearer $TOKEN"

# 4) Live log lines for a job
curl -s "http://<SERVER_IP>/api/v1/jobs/EXT-20260805-000010/logs" -H "Authorization: Bearer $TOKEN"

# 5) Email delivery status for a job
curl -s http://<SERVER_IP>/api/v1/reports/EXT-20260805-000010/emails -H "Authorization: Bearer $TOKEN"

# Pretty-print any of the above by appending:  | python3 -m json.tool
```

### Via the database (no login needed)

```bash
# open a psql shell
$DC exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB>
```
```sql
-- recent jobs
SELECT job_id, status, requested_shortcodes, created_at, finished_at, error_message
FROM extraction_jobs ORDER BY created_at DESC LIMIT 20;

-- a job's report
SELECT csv_row_count, source_file_count, missing_file_count, zip_size_bytes, source_files
FROM report_metadata WHERE job_id = 'EXT-20260805-000010';

-- a job's log lines
SELECT created_at, level, message FROM job_logs
WHERE job_id = 'EXT-20260805-000010' ORDER BY id;

-- email deliveries
SELECT recipient, method, status, error, sent_at FROM email_deliveries
WHERE job_id = 'EXT-20260805-000010';
```
(One-liner without a shell: `$DC exec db psql -U <user> -d <db> -c "SELECT job_id,status FROM extraction_jobs ORDER BY created_at DESC LIMIT 10;"`)

### Diagnostic CLIs (api container)

```bash
$DC exec api python -m app.scripts.s3_check --from 2026-08-01 --to 2026-08-02   # what files exist
$DC exec api python -m app.scripts.extract_check --shortcodes 8890 --from 2026-08-01 --to 2026-08-01
```

---

## 2. Container management

```bash
$DC ps                       # status of all services
$DC up -d --build            # (re)build + start everything
$DC up -d --build api        # just one service
$DC restart nginx            # restart one service (fixes 502 after a rebuild)
$DC up -d --force-recreate api worker beat   # reload backend/.env (no rebuild)
$DC stop                     # stop all (keeps data)
$DC start                    # start again
$DC down                     # stop + remove containers (volumes KEPT)
$DC up -d --scale worker=3   # run 3 workers
$DC exec api sh              # shell inside the api container
docker stats                 # live CPU/memory per container
docker system df             # disk used by images/volumes
docker image prune -f        # reclaim space from old images (safe)
```

Health of a running container:
```bash
$DC ps                       # STATUS column shows healthy/unhealthy for db & redis
curl -s http://<SERVER_IP>/api/v1/ready   # db / redis / s3 checks
```

---

## 3. Log management

```bash
# follow logs (Ctrl-C to stop)
$DC logs -f api
$DC logs -f worker           # extraction + email progress
$DC logs -f nginx            # 502s, proxy errors
$DC logs -f beat             # retention schedule

# last N lines
$DC logs --tail=100 api

# only errors / filter
$DC logs api 2>&1 | grep -Ei "error|traceback"
$DC logs worker 2>&1 | grep "EXT-20260805-000010"    # one job across the worker log

# since a time
$DC logs --since 30m worker

# save to a file
$DC logs --no-color api > api.log
```

Notes:
- **Worker logs** show extraction (`S3 discovery`, `Extraction done`, Drive upload) and
  email results — the first place to look for a failed job/email.
- **Per-job logs** are also in the DB (`job_logs`) and the UI live console (§1).
- Log level is `LOG_LEVEL` in `backend/.env` (`DEBUG` for more detail).

---

## 4. Database management

```bash
# psql shell
$DC exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB>

# run a single query
$DC exec db psql -U <user> -d <db> -c "SELECT count(*) FROM extraction_jobs;"

# list tables
$DC exec db psql -U <user> -d <db> -c "\dt"
```

### Backup & restore

```bash
# backup
$DC exec db pg_dump -U <user> <db> > backup_$(date +%F).sql

# restore (into a running, empty db)
cat backup_2026-08-05.sql | $DC exec -T db psql -U <user> -d <db>
```

### Migrations

```bash
$DC exec api alembic current            # current schema version
$DC exec api alembic history            # all migrations
$DC exec api alembic upgrade head       # apply (also runs automatically on api start)
$DC exec api alembic downgrade -1       # revert one (use with care)
```

### Reset the database (destroys metadata; artifacts/S3 untouched)

```bash
$DC down
docker volume ls | grep db_data         # find the exact name (e.g. deploy_db_data)
docker volume rm deploy_db_data
$DC up -d --build
$DC exec api python -m app.scripts.seed
```

### Useful maintenance queries

```sql
-- admin manage-everything view: who did what recently
SELECT created_at, action, resource_id, ip_address FROM audit_logs
ORDER BY created_at DESC LIMIT 50;

-- stuck jobs (processing too long)
SELECT job_id, status, started_at FROM extraction_jobs
WHERE status = 'PROCESSING' AND started_at < now() - interval '1 hour';

-- storage: reports past expiry that should be cleaned
SELECT job_id, expires_at FROM report_metadata WHERE expires_at < now();
```

---

## 5. Troubleshooting quick reference

| Symptom | Check | Fix |
|---------|-------|-----|
| Site unreachable | `$DC ps`; is port 80 open? | `sudo ufw allow 80/tcp`; `$DC up -d` |
| `502 Bad Gateway` (api Up) | nginx cached old container IP | `$DC restart nginx` |
| `502` (api not Up) | `$DC logs --tail=50 api` | fix the error shown (usually `.env`) |
| Login fails for everyone | `$DC logs api`; `JWT_SECRET` set? | fill `backend/.env`, recreate api |
| `/ready` db error | `DATABASE_URL` host=`db`, `@`→`%40`, creds match `deploy/.env` | fix + `up -d --force-recreate api` |
| `/ready` redis error | `REDIS_URL=redis://redis:6379/0` | fix + recreate api/worker |
| `/ready` s3 error | `AWS_*`, `S3_BUCKET`; `S3_ENDPOINT_URL` empty | fix; test `s3_check` |
| Job stuck in `PENDING` | is a worker running? `$DC ps` / `$DC logs worker` | start/scale worker; check broker URL |
| Job `FAILED` | job's `error_message` (API/DB) + `$DC logs worker` | act on the message |
| Job scanned too few rows | job's **Files scanned** list / `s3_check` | confirm the date range has data / all parts |
| Email `FAILED` 403 scopes | delivery `error` | add `drive.file` scope — [gmail-drive-setup.md](gmail-drive-setup.md) |
| Downloads 404/410 | report expired (`retention`) or not owner | re-run the job; check ownership |
| Disk filling up | `docker system df`; old reports | `docker image prune -f`; retention runs daily |
| Blank field parsed as `# …` | inline comment after an empty `.env` value | remove inline comments |

When in doubt: **worker logs** for jobs/email, **api logs** for auth/HTTP, **nginx logs**
for 502s, **`/ready`** for dependency health, and the **`audit_logs`/`job_logs`** tables
for a per-user / per-job trail.
