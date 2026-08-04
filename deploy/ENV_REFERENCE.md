# ENV Reference — how to obtain every value

This explains **where each `.env` value comes from** and **how to generate/find it**.

There are two env files:

| File | Purpose | Template |
|------|---------|----------|
| `backend/.env` | The application's runtime configuration (all app settings) | `backend/.env.example` |
| `deploy/.env` | Compose-level infra: Postgres creds, domain, frontend build args | `deploy/.env.example` |

> **Golden rule:** nothing is hardcoded in code. Every value below is read from these
> files at runtime (backend) or build time (frontend `NEXT_PUBLIC_*`).

---

## A. App settings (`backend/.env`)

### APP_ENV
`development` | `staging` | `production`. Set to **`production`** on the server.

### APP_NAME
Any short identifier, e.g. `client-data-extraction`. Free choice.

### API_V1_PREFIX
Keep the default `/api/v1` unless you have a reason to change it. The nginx config and
frontend `NEXT_PUBLIC_API_BASE_URL` assume `/api/v1`.

### BACKEND_CORS_ORIGINS
Comma-separated list of the **frontend origin(s)** the browser will use.
- Production behind nginx (same domain): `https://your-domain.com`
- Local dev: `http://localhost:3000`

### LOG_LEVEL
`INFO` normally; `DEBUG` while troubleshooting.

---

## B. Security / Auth (`backend/.env`)

### JWT_SECRET  ⭐ required
A long random string used to sign login tokens. **Generate one — never reuse an
example.**
```bash
# any ONE of these:
openssl rand -hex 48
python -c "import secrets; print(secrets.token_hex(48))"
```
Windows PowerShell:
```powershell
python -c "import secrets; print(secrets.token_hex(48))"
```
Keep it secret. Rotating it later logs everyone out (tokens become invalid).

### JWT_ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES / REFRESH_TOKEN_EXPIRE_DAYS / PASSWORD_HASH_SCHEME / LOGIN_RATE_LIMIT_*
Sensible defaults are provided. Change only if you have a policy reason.

---

## C. Database (`backend/.env` + `deploy/.env`)  ⭐ required

### DATABASE_URL
SQLAlchemy URL for Postgres:
```
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```
- **Using the bundled Postgres (compose):** `HOST` = `db`, and `USER`/`PASSWORD`/
  `DBNAME` must equal `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` in
  `deploy/.env`. Example pair:
  - `deploy/.env`: `POSTGRES_USER=app`, `POSTGRES_PASSWORD=S0meStrongPass`, `POSTGRES_DB=extraction`
  - `backend/.env`: `DATABASE_URL=postgresql+psycopg://app:S0meStrongPass@db:5432/extraction`
- **Using a managed/existing Postgres (RDS, etc.):** use that server's host, port,
  and the credentials your DBA created. You typically create a DB + user like:
  ```sql
  CREATE DATABASE extraction;
  CREATE USER appuser WITH PASSWORD 'S0meStrongPass';
  GRANT ALL PRIVILEGES ON DATABASE extraction TO appuser;
  ```
- **Local dev without a server:** `sqlite:///./app.db` works for early phases.

Generate a strong DB password:
```bash
openssl rand -base64 24
```

---

## D. Redis / Celery (`backend/.env`)  ⭐ REDIS_URL required

### REDIS_URL
```
redis://HOST:6379/0
```
- **Compose:** `redis://redis:6379/0` (host = the `redis` service name).
- **Managed Redis:** the connection string from your provider (may include a
  password: `redis://:password@host:6379/0`, or `rediss://` for TLS).

### CELERY_BROKER_URL / CELERY_RESULT_BACKEND
Separate Redis logical DBs keep queues and results tidy:
- `CELERY_BROKER_URL=redis://redis:6379/1`
- `CELERY_RESULT_BACKEND=redis://redis:6379/2`

If left blank, both fall back to `REDIS_URL`.

### CELERY_TASK_TIME_LIMIT / SOFT_TIME_LIMIT / WORKER_CONCURRENCY / MAX_RETRIES
Tuning for the long, large-file extraction jobs. Defaults are generous
(`TIME_LIMIT=21600` = 6h). Raise if a single extraction can exceed that.

---

## E. AWS / S3 (`backend/.env`) — the source of truth (read-only)

You need **read-only** access to the bucket that holds the daily CSV files.

### AWS_REGION
The region the bucket lives in. Find it: AWS Console → **S3** → click the bucket →
**Properties** → "AWS Region" (e.g. `us-east-1`, `eu-west-1`).

### S3_BUCKET
The bucket name, e.g. `bk-kannel` (no `s3://`, no path).

### S3_PREFIX
The folder path inside the bucket where the daily files live, e.g.
`daily-jasminfiles-fatib`. From the example object
`s3://bk-kannel/daily-jasminfiles-fatib/daily-data_2023-09-01.csv`, the prefix is
`daily-jasminfiles-fatib`.

### S3_FILE_TEMPLATE
The daily filename pattern. Default `daily-data_{yyyy}-{mm}-{dd}.csv` matches the
example. Adjust if names differ.

### S3_DISCOVERY_MODE
`list` (default; lists the prefix and matches dates — robust) or `template` (builds
exact keys — fastest when naming is perfectly predictable).

### AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
Two ways to authenticate:

**Option 1 — IAM user access keys** (works anywhere, incl. on-prem VM):
1. AWS Console → **IAM** → **Users** → **Create user** (e.g. `extraction-reader`).
2. Do **not** give console access; you only need programmatic keys.
3. Attach a **read-only** policy scoped to the bucket (create it under IAM → Policies):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [
           "arn:aws:s3:::bk-kannel",
           "arn:aws:s3:::bk-kannel/*"
         ]
       }
     ]
   }
   ```
4. After creating the user → **Security credentials** → **Create access key** →
   choose "Application running outside AWS" → copy the **Access key ID** and
   **Secret access key** into `backend/.env`. (The secret is shown only once.)

**Option 2 — IAM role** (only if the app runs on EC2/ECS): attach the same read-only
policy to the instance/task role and **leave both key variables blank** — boto3 uses
the role automatically. Preferred in AWS environments (no long-lived keys).

### S3_ENDPOINT_URL
Leave **blank** for real AWS S3. Set only for S3-compatible stores (MinIO, etc.).

### S3_MAX_RETRIES
Retry attempts on throttling. Default `5` is fine.

---

## F. CSV extraction (`backend/.env`)

These describe the **inside** of the CSV files. Confirm them against one real file's
header row (open the first lines of a `daily-data_*.csv`).

### CSV_SHORTCODE_COLUMN
The column the shortcode is matched against — **`source_addr`** in your case
(e.g. keep rows where `source_addr == 8990`).

### CSV_DELIMITER
`,` for standard CSV. Use the real separator if different.

### CSV_HAS_HEADER
`true` if files start with a header row.

### CSV_COMPRESSION
`none` for plain `.csv`. Set `gzip` if the daily files are gzip-compressed (matters a
lot for 1 GB files).

### CSV_TIMESTAMP_COLUMN / CSV_TIMESTAMP_FORMAT
Only needed if you want to filter **within** a day by time. Set the timestamp column
name and its `strptime` format (e.g. `%Y-%m-%d %H:%M:%S`). Leave blank to select
whole in-range files only.

### EXTRACTION_PARALLEL_FILES
`true` to process the (independent) daily files concurrently across workers — faster
for large ranges.

---

## G. Jobs / storage / retention (`backend/.env`)

### JOB_ID_STRATEGY
`ulid` (recommended, time-sortable) or `uuid4`.

### MAX_RANGE_DAYS
Guardrail on how wide a single extraction can be (default 92).

### REPORT_STORAGE_PATH
Where generated CSV/ZIP/metadata are stored. In compose this is `/app/storage`
(mapped to the `report_storage` volume). On bare metal use an absolute path on a disk
with enough space for the ZIPs.

### REPORT_RETENTION_DAYS
Auto-delete generated reports after N days (default 30). `0` = keep indefinitely.

### ZIP_COMPRESSION_LEVEL
`0`–`9` (default 6). Higher = smaller/slower.

---

## H. Email (`backend/.env`)

Pick **one** provider via `EMAIL_PROVIDER`.

### EMAIL_FROM_ADDRESS
The "from" address recipients see, e.g. `reports@your-domain.com`. Must be an address
you're allowed to send from (verified in SES, or a real mailbox for SMTP).

### EMAIL_PROVIDER = ses  (AWS SES)
1. AWS Console → **SES** → **Verified identities** → verify your domain (add the DNS
   records they give you) or a single sender email.
2. New SES accounts are in **sandbox** (can only send to verified addresses). Request
   **production access** to email anyone.
3. Set `SES_REGION` to the SES region (SES is region-specific). Credentials: SES uses
   your AWS credentials/role (same style as S3; the IAM principal needs
   `ses:SendEmail` / `ses:SendRawEmail`).

### EMAIL_PROVIDER = smtp
Use any SMTP server. You get these from your mail provider:
- `SMTP_HOST` (e.g. `smtp.your-provider.com`)
- `SMTP_PORT` (usually `587` for STARTTLS)
- `SMTP_USERNAME` / `SMTP_PASSWORD` (a mailbox login, an app password, or **SES SMTP
  credentials** if you use SES over SMTP)
- `SMTP_USE_TLS=true`

### EMAIL_MAX_ATTACHMENT_BYTES
Reports larger than this are emailed as a **secure link** instead of an attachment
(default 10 MB).

### DOWNLOAD_LINK_EXPIRE_MINUTES
How long an emailed download link stays valid (default 60).

---

## I. n8n integration (`backend/.env`) — external, optional

Only needed when you wire up the external n8n (on `192.168.255.170`).

### N8N_BASE_URL
The n8n instance URL, e.g. `http://192.168.255.170:5678`.

### N8N_SERVICE_TOKEN
A token **you generate** (like a JWT_SECRET) and give to n8n so it can call the
scoped `/internal` API. Generate: `openssl rand -hex 32`. Store the same value in n8n's
HTTP request auth.

### N8N_WEBHOOK_URL / N8N_WEBHOOK_SECRET
If you want the backend to push job-completion events to n8n: the webhook URL from
n8n, and a shared secret (`openssl rand -hex 32`) used to HMAC-sign the payload so
n8n can verify it.

---

## J. Compose-level (`deploy/.env`)

### POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
Credentials for the bundled Postgres container. Must match `DATABASE_URL` in
`backend/.env` (see section C). Generate the password with `openssl rand -base64 24`.

### API_WORKERS / CELERY_WORKER_CONCURRENCY
How many API worker processes and Celery worker threads to run. Scale to the VM's CPU.

### NEXT_PUBLIC_API_BASE_URL  (build arg)
The URL the **browser** uses to reach the API. Behind nginx on one domain:
`https://your-domain.com/api/v1`. **Changing this requires rebuilding the frontend
image** (it's compiled into the bundle).

### NEXT_PUBLIC_MAX_RANGE_DAYS / JOB_POLL_INTERVAL_MS / ENABLE_ASSISTANT
UI behavior toggles. Safe defaults provided.

---

## Quick checklist

- [ ] `JWT_SECRET` generated (not the example)
- [ ] `POSTGRES_*` set in `deploy/.env`; `DATABASE_URL` in `backend/.env` matches, host `db`
- [ ] `REDIS_URL` = `redis://redis:6379/0`
- [ ] AWS read-only key/role + `AWS_REGION`, `S3_BUCKET`, `S3_PREFIX`
- [ ] `CSV_SHORTCODE_COLUMN=source_addr` + `CSV_COMPRESSION` confirmed from a real file
- [ ] Email provider configured + `EMAIL_FROM_ADDRESS` verified
- [ ] `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` point at your real domain
- [ ] `deploy/.env` and `backend/.env` created (never committed)
