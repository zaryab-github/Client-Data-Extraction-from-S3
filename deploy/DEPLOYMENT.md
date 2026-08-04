# Deployment Guide (nginx + Docker Compose)

Step-by-step guide to host the Client Data Extraction & Delivery System behind
**nginx**. Every value you need to fill in is explained in
[ENV_REFERENCE.md](ENV_REFERENCE.md).

```
Client ─▶ nginx (:80) ─┬─▶ frontend (Next.js, :3000)
                       └─▶ api (FastAPI, :8000) ─▶ redis, db, worker, beat
```

All services run as containers from `deploy/docker-compose.prod.yml`.

> ## ⚡ Your setup: IP only, no public domain
> You're deploying to a **server IP** (no domain). The default config is **HTTP over
> the IP** — you do **not** need certbot/Let's Encrypt (it can't issue certs for a bare
> IP). Follow **§0 → §1 → §2 → §5 → §6**. **Skip §3 and §4** (domain + Let's Encrypt).
> Everywhere below that says `your-domain.com`, use `http://<SERVER_IP>` instead.
>
> Want traffic encrypted on the network anyway (recommended, since login tokens
> travel over it)? Use a **self-signed cert for the IP** — see
> [§4-ALT](#4-alt-optional-self-signed-https-for-an-ip). Otherwise plain HTTP is fine
> on a trusted internal network.

---

## 0. Prerequisites

On the server (a Linux VM is assumed):

- **Docker Engine + Docker Compose plugin**
  ```bash
  # Docker's convenience script (Ubuntu/Debian):
  curl -fsSL https://get.docker.com | sh
  docker compose version      # confirm the compose plugin is present
  ```
- **Open ports 80 and 443** to the server (cloud security group / VM firewall).
- **A domain name** (for public TLS) pointing at the server's public IP:
  create a DNS **A record** `your-domain.com → <server-public-IP>`.
  - No public domain (internal VM only)? You can still run **HTTP-only** — see
    [§7](#7-internal-only-http-only-deployment). TLS via Let's Encrypt needs a public
    domain.
- Git installed.

> **Windows note:** these server steps are for the Linux host that will run the app.
> Your local Windows machine is only used for development. Commands below are shown as
> bash for the server.

---

## 1. Get the code

```bash
git clone <your-repo-url> client-data-extraction
cd client-data-extraction
```

---

## 2. Configure environment files

You create **three** files (all gitignored). See [ENV_REFERENCE.md](ENV_REFERENCE.md)
for how to obtain each value.

```bash
# 2a. Application config
cp backend/.env.example backend/.env

# 2b. Compose infra + frontend build args
cp deploy/.env.example deploy/.env
```

Now edit them:

**`deploy/.env`** — set:
- `POSTGRES_USER`, `POSTGRES_PASSWORD` (generate: `openssl rand -base64 24`), `POSTGRES_DB`
- `NEXT_PUBLIC_API_BASE_URL=http://<SERVER_IP>/api/v1`  ← your server's IP

**`backend/.env`** — set at minimum:
- `APP_ENV=production`
- `JWT_SECRET=` → `openssl rand -hex 48`
- `DATABASE_URL=postgresql+psycopg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@db:5432/<POSTGRES_DB>`
  (must match `deploy/.env`, host = `db`)
- `REDIS_URL=redis://redis:6379/0`
- `CELERY_BROKER_URL=redis://redis:6379/1`, `CELERY_RESULT_BACKEND=redis://redis:6379/2`
- `BACKEND_CORS_ORIGINS=http://<SERVER_IP>`   ← your server's IP (no trailing slash)
- AWS/S3: `AWS_REGION`, `S3_BUCKET`, `S3_PREFIX`, and read-only creds (or IAM role)
- CSV: `CSV_SHORTCODE_COLUMN=source_addr`, `CSV_COMPRESSION` (none/gzip)
- Email: `EMAIL_PROVIDER` + its settings + `EMAIL_FROM_ADDRESS`

> Using an IP means the default `app.http-only.conf` (already the default in the
> compose file) serves the app on port 80 — no domain edits needed.

> S3, CSV, and email can be left as placeholders for Phase 1 bring-up (health checks
> work without them); fill them before Phase 4/7 features are used.

**Verify consistency:** the DB user/password/name must be identical in both files.

---

## 3. Point nginx at your domain  · _(DOMAIN ONLY — skip for IP)_

> Skip this whole section if you're using an IP. The default `app.http-only.conf`
> uses `server_name _;` which already matches any IP/host.

Edit `deploy/nginx/app.conf` and replace **`your-domain.com`** (appears twice) with
your real domain.

---

## 4. Obtain TLS certificates (Let's Encrypt)  · _(DOMAIN ONLY — skip for IP)_

The nginx config expects certs at `deploy/nginx/certs/fullchain.pem` and
`privkey.pem`. Get them with **certbot** using the HTTP-01 (webroot) challenge.

**4a. Temporarily start nginx in HTTP mode** so the ACME challenge can be served.
Easiest path: bring the stack up first with the HTTP-only config, get the cert, then
switch to TLS.

```bash
# Use the HTTP-only server block for the first boot:
#   edit docker-compose.prod.yml → nginx volumes → mount app.http-only.conf
#   (or temporarily copy it over app.conf)
docker compose -f deploy/docker-compose.prod.yml up -d --build nginx frontend api
```

**4b. Run certbot** (as a one-off container sharing the webroot + a certs volume):

```bash
docker run --rm \
  -v "$(pwd)/deploy/nginx/certbot-www:/var/www/certbot" \
  -v "$(pwd)/deploy/nginx/letsencrypt:/etc/letsencrypt" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d your-domain.com --email you@example.com --agree-tos --no-eff-email
```

**4c. Copy the issued cert into the path nginx mounts:**

```bash
cp deploy/nginx/letsencrypt/live/your-domain.com/fullchain.pem deploy/nginx/certs/fullchain.pem
cp deploy/nginx/letsencrypt/live/your-domain.com/privkey.pem   deploy/nginx/certs/privkey.pem
```

**4d. Switch nginx back to the TLS config** (`app.conf`, the default in the compose
file) and reload:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate nginx
```

> **Renewal:** certs last 90 days. Re-run 4b–4d, or add a cron job that renews and
> copies the files then runs `docker compose ... exec nginx nginx -s reload`. Example
> monthly cron:
> ```
> 0 3 1 * * cd /path/client-data-extraction && docker run --rm -v "$PWD/deploy/nginx/certbot-www:/var/www/certbot" -v "$PWD/deploy/nginx/letsencrypt:/etc/letsencrypt" certbot/certbot renew --webroot -w /var/www/certbot && cp deploy/nginx/letsencrypt/live/your-domain.com/*.pem deploy/nginx/certs/ && docker compose -f deploy/docker-compose.prod.yml exec nginx nginx -s reload
> ```

---

## 4-ALT. (Optional) Self-signed HTTPS for an IP

Plain HTTP over an IP is fine on a trusted internal network. If you want the traffic
encrypted anyway (recommended — login tokens travel over it), generate a **self-signed
certificate for the IP** and use the TLS config. Browsers will show a one-time "not
trusted" warning (expected for self-signed).

```bash
# From the repo root — creates fullchain.pem + privkey.pem valid for the IP:
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out    deploy/nginx/certs/fullchain.pem \
  -subj   "/CN=<SERVER_IP>" \
  -addext "subjectAltName=IP:<SERVER_IP>"
```

Then switch nginx to the TLS config:
1. In `deploy/nginx/app.conf`, set `server_name <SERVER_IP>;` (both server blocks) and
   remove the `.well-known/acme-challenge` + redirect bits are fine to leave.
2. In `deploy/docker-compose.prod.yml`, comment the `app.http-only.conf` mount and
   uncomment the `app.conf` + `certs` mounts.
3. Set `NEXT_PUBLIC_API_BASE_URL=https://<SERVER_IP>/api/v1` and
   `BACKEND_CORS_ORIGINS=https://<SERVER_IP>`, then rebuild the frontend.
4. `docker compose -f deploy/docker-compose.prod.yml up -d --build`.

---

## 5. Build and start the full stack

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml ps        # all services healthy?
```

This builds the backend + frontend images and starts: `db`, `redis`, `api`,
`worker`, `beat`, `frontend`, `nginx`.

> **Database migrations (Phase 2+):** the `api` service runs `alembic upgrade head`
> automatically on start, so tables are created for you. To run them manually:
> ```bash
> docker compose -f deploy/docker-compose.prod.yml exec api alembic upgrade head
> ```

### 5.1 Seed the first admin + roles (Phase 2)

Set these in `backend/.env` first:
```ini
FIRST_ADMIN_EMAIL=admin@yourcompany.com
FIRST_ADMIN_PASSWORD=<a strong password>
SEED_DEMO_DATA=true      # optional: also creates demo shortcodes 8990, 1234
```
Then run the seed (idempotent — safe to re-run):
```bash
docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api   # pick up new env
docker compose -f deploy/docker-compose.prod.yml exec api python -m app.scripts.seed
```
This creates the `admin`/`analyst`/`viewer` roles with permissions and your first
admin user. You can now sign in at `http://<SERVER_IP>` with those credentials.

---

## 6. Verify

```bash
# From the server (IP deployment — use your server IP):
curl -fsS http://<SERVER_IP>/api/v1/health     # → {"status":"ok",...}
curl -fsS http://<SERVER_IP>/api/v1/ready       # → {"status":"ready","checks":{...}}
# (Domain + TLS deployment: use https://your-domain.com/... instead.)
```

Then open **http://<SERVER_IP>** in a browser — the frontend foundation page loads.
`http://<SERVER_IP>/docs` shows the API docs (disable in prod if desired by removing
that nginx location).

Check logs if anything is off:
```bash
docker compose -f deploy/docker-compose.prod.yml logs -f api
docker compose -f deploy/docker-compose.prod.yml logs -f nginx
```

---

## 7. Internal-only / HTTP-only deployment

No public domain yet (e.g. reachable only at an internal IP like the n8n VM)? Run
without TLS:

1. In `deploy/docker-compose.prod.yml`, mount `app.http-only.conf` instead of
   `app.conf` in the `nginx` service.
2. Set `NEXT_PUBLIC_API_BASE_URL=http://<server-ip>/api/v1` in `deploy/.env` and
   `BACKEND_CORS_ORIGINS=http://<server-ip>` in `backend/.env`.
3. `docker compose -f deploy/docker-compose.prod.yml up -d --build`.
4. Reach it at `http://<server-ip>/`.

⚠️ HTTP sends JWTs unencrypted — use this only on a trusted internal network, and
switch to TLS before any public exposure.

---

## 8. Alternative: nginx installed on the host (not in Docker)

If you prefer nginx as a system service on the VM:

1. Remove/stop the `nginx` service in the compose file and **publish** the app ports
   to localhost by adding to `api`: `ports: ["127.0.0.1:8000:8000"]` and to
   `frontend`: `ports: ["127.0.0.1:3000:3000"]`.
2. Install nginx: `sudo apt install nginx`.
3. Copy `deploy/nginx/host.conf` → `/etc/nginx/sites-available/extraction.conf`, edit
   the domain, then:
   ```bash
   sudo ln -s /etc/nginx/sites-available/extraction.conf /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
4. TLS the easy way: `sudo apt install certbot python3-certbot-nginx` then
   `sudo certbot --nginx -d your-domain.com` (certbot edits the config and sets up
   auto-renewal for you).

---

## 9. Redeployment (updates)

**Code update (same config):**
```bash
git pull
docker compose -f deploy/docker-compose.prod.yml build
# Phase 2+: run migrations first
# docker compose -f deploy/docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f deploy/docker-compose.prod.yml up -d
```

**Config-only change** (edited `backend/.env`):
```bash
docker compose -f deploy/docker-compose.prod.yml up -d --force-recreate api worker beat
```

**Frontend URL / build-arg change** (edited `NEXT_PUBLIC_*` in `deploy/.env`):
```bash
docker compose -f deploy/docker-compose.prod.yml build frontend
docker compose -f deploy/docker-compose.prod.yml up -d frontend
```

**Rollback:**
```bash
git checkout <previous-tag>
docker compose -f deploy/docker-compose.prod.yml up -d --build
```
Prefer forward fixes over DB downgrades; tag releases (`git tag vX.Y.Z`) so rollback
targets are clear. Local report artifacts are regenerable — a rollback never risks the
S3 source (read-only).

---

## 10. Operations

- **Scale workers:** `docker compose -f deploy/docker-compose.prod.yml up -d --scale worker=3`
  (the shared `report_storage` volume keeps artifacts visible to `api`).
- **Exactly one `beat`** — never scale it above 1.
- **Backups:** dump Postgres regularly:
  ```bash
  docker compose -f deploy/docker-compose.prod.yml exec db \
    pg_dump -U <POSTGRES_USER> <POSTGRES_DB> > backup_$(date +%F).sql
  ```
  Report artifacts are regenerable from S3, so backing them up is optional.
- **Logs:** `docker compose -f deploy/docker-compose.prod.yml logs -f <service>`.
- **Stop / start:**
  ```bash
  docker compose -f deploy/docker-compose.prod.yml stop
  docker compose -f deploy/docker-compose.prod.yml up -d
  ```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `502 Bad Gateway` from nginx | api/frontend not up yet or crashed | `docker compose ... ps` / `logs api` |
| `502` even though `api` is Up | nginx cached the old container IP after a rebuild | `docker compose ... restart nginx` (the resolver-based config avoids this going forward) |
| `/api/v1/ready` → `redis error` | Redis not reachable | check `REDIS_URL` = `redis://redis:6379/0`; `logs redis` |
| `/api/v1/ready` → `database error` | Wrong `DATABASE_URL` / creds mismatch | ensure `backend/.env` matches `deploy/.env`, host `db` |
| api exits: "Missing required environment configuration" | `JWT_SECRET`/`DATABASE_URL`/`REDIS_URL` blank | fill `backend/.env` |
| Browser calls go to wrong API URL | `NEXT_PUBLIC_API_BASE_URL` wrong at build | fix `deploy/.env`, rebuild `frontend` |
| TLS error / cert not found | certs missing at `deploy/nginx/certs/` | complete §4, or use http-only config |
| Downloads time out on large ZIPs | proxy timeout too low | already set to 3600s + buffering off in `app.conf` |
| CORS errors in browser | `BACKEND_CORS_ORIGINS` doesn't match the site origin | set it to `https://your-domain.com` |

---

## Files in `deploy/`

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Dev stack (db, redis, api, worker) |
| `docker-compose.prod.yml` | Production stack (adds nginx, frontend, beat) |
| `.env.example` | Compose-level infra + frontend build args |
| `nginx/app.conf` | TLS reverse proxy (Docker nginx) |
| `nginx/app.http-only.conf` | HTTP-only reverse proxy (initial/internal) |
| `nginx/host.conf` | Config for nginx installed on the host |
| `nginx/certs/` | TLS cert + key (gitignored) |
| `nginx/certbot-www/` | ACME challenge webroot |
| `ENV_REFERENCE.md` | How to obtain every `.env` value |
| `DEPLOYMENT.md` | This guide |
