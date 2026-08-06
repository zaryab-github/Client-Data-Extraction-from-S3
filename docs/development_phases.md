# Development Phases

This document defines the phased implementation plan for the **Production-Ready Client Data Extraction & Delivery System**.

The phases below are derived from the approved project requirements and implementation instructions. Each phase is intended to be implemented independently and must not automatically proceed to the next phase.

## Core Implementation Rules

- All configurable values must come from `.env`.
- Never hardcode secrets, credentials, URLs, IPs, AWS settings, S3 bucket names, database URLs, Redis URLs, JWT secrets, email settings, local storage paths, retention settings, n8n URLs, or API keys.
- Create `.env.example`.
- Add `.env` to `.gitignore`.
- Do not expose AWS credentials to the frontend.
- The backend must independently enforce authentication and authorization.
- The frontend must never access S3 directly.
- Client CSV source files in S3 are read-only and must never be modified or deleted.
- Do not introduce unrelated features.
- Complete lightweight tests for each phase before stopping.
- Do not proceed automatically to the next phase.

---

## Cross-Cutting Notes & Open Decisions

These apply across phases and resolve gaps found during review:

- **Admin & management** (create/list users, assign roles, create/list shortcodes,
  grant/revoke user→shortcode access) is delivered in **Phase 7** as backend admin
  APIs + admin screens. Until then, seed data via `python -m app.scripts.seed`
  (roles/permissions, first admin, and `SEED_DEMO_DATA` shortcodes).
- **Audit log model** is introduced in **Phase 6** (with the jobs pipeline) and used
  by Phases 8–9. Record: user, action, resource, IP/user-agent, timestamp, outcome.
- **Job ID format** (Phase 5): the human-friendly `EXT-YYYYMMDD-NNNNNN` is
  **sequential and enumerable** (reveals daily volume, guessable). Acceptable because
  every download is ownership-checked, but if enumeration resistance is wanted, add a
  random suffix (e.g. `EXT-20260804-000001-7F3A`) or use ULID. Decide at Phase 5.
- **CSV header dependency** (blocks Phase 4, not Phase 3): confirm one real
  `daily-data_*.csv` header first — exact shortcode column (default `source_addr`),
  delimiter, plain vs. gzip, and timestamp column/format (only if sub-day time
  filtering is needed). All are `.env`-configurable; this only sets correct defaults.
- **Tests touching S3** use a mock (moto/stub) so they run without live AWS; keep an
  optional real-connection smoke gated by `.env`.

---

Implement Phase 1: Project Foundation.

Use the architecture approved in the previous analysis.

Create:

1. Frontend project.
2. FastAPI backend.
3. Database connection layer.
4. Redis configuration.
5. Celery configuration.
6. Project folder structure.
7. .env.example.
8. .gitignore.
9. README.

All configuration must come from .env.

Do not hardcode any:

* Secrets
* Credentials
* URLs
* IPs
* AWS settings
* S3 bucket names
* Database URLs
* Redis URLs

Do not implement business logic yet.

Perform lightweight tests only:

* Backend starts.
* Frontend starts.
* Environment configuration loads.
* Database configuration loads.
* Redis configuration loads.
* Celery configuration loads.

Do not proceed to Phase 2 automatically.




--------------


Implement Phase 2: Authentication and Authorization.

Implement:

1. User model.
2. Role model.
3. Shortcode model.
4. User-to-shortcode permission model.
5. Secure login.
6. Logout.
7. JWT or secure session authentication.
8. RBAC.
9. Shortcode-level permissions.
10. Protected APIs.
11. Frontend login page.
12. Protected frontend routes.

Backend must independently validate every permission.

A user must only extract data for authorized shortcodes.

All authentication secrets and configuration must come from .env.

Lightweight tests:

* Valid login.
* Invalid login rejection.
* Unauthenticated API rejection.
* Authorized shortcode access.
* Unauthorized shortcode rejection.

Do not implement S3 extraction yet.





---------------------

Implement Phase 3: AWS S3 Integration.

Requirements:

1. Create an S3 service layer.
2. Use AWS SDK.
3. Load AWS configuration from .env.
4. List relevant CSV files based on date/time range.
5. Support configurable S3 bucket.
6. Support configurable S3 source prefix.
7. Keep source CSV files read-only.
8. Never delete or modify source CSVs.
9. Add proper error handling.
10. Add logging.

Do not expose AWS credentials to frontend.

Lightweight tests:

* S3 authentication.
* List files.
* Date-based file selection.
* Missing file handling.
* Invalid S3 configuration handling.

Do not implement the full extraction engine yet.



------------

Implement Phase 4: CSV Extraction Engine.

The extraction engine must:

1. Receive a validated extraction request.
2. Identify multiple relevant CSV files from S3.
3. Process multiple CSV files.
4. Filter by one or multiple shortcodes inside the files (CSV Tab). Select each row of matching.
5. Filter by date/time.
6. Combine matching records.
7. Generate a new CSV file.
8. Preserve required CSV columns.
9. Handle no matching records.
10. Avoid unnecessarily loading very large files into memory.
11. Never modify source CSV files.

> Note: the shortcode is matched against a column INSIDE the CSV (default
> `source_addr`, e.g. `source_addr == 8990`), all configurable via `.env`. Confirm
> the real header/format (and gzip) before implementing — see Cross-Cutting Notes.

The extraction engine must not bypass authentication or authorization.

Lightweight tests:

* One CSV.
* Multiple CSVs.
* One shortcode.
* Multiple shortcodes.
* Date filtering.
* Date/time filtering.
* No matching records.

Do not implement Celery background processing yet.





-------------



Implement Phase 5: Job ID and Report Storage.

Requirements:

1. Generate a unique Job ID for every extraction request.

Example:
EXT-20260804-000001

2. Create a job-specific local storage directory.

Example:

storage/jobs/EXT-20260804-000001/

3. Generate:

* extracted_data.csv
* EXT-20260804-000001.zip
* metadata.json

4. ZIP must contain the generated CSV.

5. Metadata must include:

* Job ID
* User
* Shortcodes
* Start date/time
* End date/time
* Files processed
* Records extracted
* Created time
* Completed time
* CSV filename
* ZIP filename
* Status

6. Store report metadata in database.
7. Store actual generated files in local application storage.
8. Make local storage path configurable through .env.
9. Make retention configurable through .env.
10. Add cleanup logic for expired reports.

Lightweight tests:

* Job ID creation.
* Job directory creation.
* CSV creation.
* ZIP creation.
* ZIP contains CSV.
* metadata.json creation.
* File cleanup.

Do not implement email yet.



---------------

Implement Phase 6: Redis and Celery Background Jobs.

Requirements:

1. Redis is the Celery broker.
2. Celery performs background extraction.
3. FastAPI creates a Job ID.
4. FastAPI creates a database extraction record.
5. FastAPI submits the job to Celery.
6. Celery worker processes multiple S3 CSV files.
7. Celery performs CSV extraction.
8. Celery generates CSV.
9. Celery creates ZIP.
10. Celery stores files locally.
11. Celery updates job metadata.
12. Introduce the audit_log model and write audit entries (job created, job
    accessed, report downloaded), plus schedule the Phase 5 retention cleanup via
    Celery beat.

Statuses:

PENDING
PROCESSING
COMPLETED
FAILED
EXPIRED

Store:

* Job ID
* User
* Shortcodes
* Date/time range
* Files processed
* Records extracted
* Processing duration
* Status
* Error details
* Local report path

Users can only access their own jobs unless they have admin permissions.

Lightweight tests:

* Job creation.
* Redis queue.
* Celery worker.
* Successful extraction.
* Failed extraction.
* Status transitions.

Do not proceed automatically.




----------------



Implement Phase 7: Frontend Dashboard & Admin Management.

Create:

1. Dashboard.
2. Authorized shortcode multi-select.
3. Start date/time.
4. End date/time.
5. Generate Report.
6. Job ID display.
7. Job status.
8. Processing status polling.
9. Completed report display.
10. ZIP download.
11. Extraction history.
12. Email report option.

Admin management (backend APIs + admin-only screens, permission-gated):

13. Create/list/update users; assign roles.
14. Create/list/update shortcodes (with optional S3 prefix overrides).
15. Grant/revoke user→shortcode access.
16. View audit logs.

The frontend must only display authorized shortcodes.

The backend must remain the final authority for authorization.

Frontend must never directly access S3.

Lightweight end-to-end tests:

* Login.
* Select shortcode.
* Create job.
* View job status.
* Completed job.
* Download ZIP.
* Unauthorized shortcode rejected.



-------------------


Implement Phase 8: Email Delivery.

Support:

1. AWS SES or SMTP.
2. All configuration through .env.
3. Email report request.
4. Email delivery status.
5. Audit logging.

For small reports:

* Allow ZIP attachment.

For large reports:

* Prefer secure temporary download link.

Store:

* Email recipient.
* Job ID.
* Email status.
* Sent timestamp.
* Error details.

Lightweight tests:

* Email request.
* Successful email.
* Failed email.
* Email status update.



----------------------


Implement Phase 9: Security Hardening.

Review the complete system.

Verify:

1. Authentication.
2. RBAC.
3. Shortcode-level authorization.
4. Backend permission validation.
5. Private S3.
6. No AWS credentials in frontend.
7. No hardcoded secrets.
8. All configuration in .env.
9. .env ignored by Git.
10. Secure report downloads.
11. Report retention.
12. Audit logs.
13. Input validation.
14. API error handling.
15. Secure logging.
16. Production HTTPS documentation.
17. Rate limiting where appropriate.

Run lightweight security tests.

Do not introduce unrelated features.


-------------------------



Implement Phase 10: Optional AI and n8n Integration.

Important:

n8n already exists on an external VM:

192.168.255.170

Do NOT install n8n.

Do NOT deploy n8n.

Create secure FastAPI APIs that external n8n workflows can use.

Required API capabilities:

1. Create extraction job.
2. Check job status.
3. Get job metadata.
4. Get download information.
5. Request email delivery.

The backend must authenticate and authorize every request.

AI/n8n must never directly access S3.

Document the n8n workflow:

User Natural Language Request
→ AI Agent
→ Extract Shortcode(s)
→ Extract Date/Time Range
→ Extract Email
→ Call FastAPI
→ Create Job
→ Poll Status
→ Job Completed
→ Download or Email

Example:

"Get ABC123 data from August 1 to August 3 and email the report."

The n8n VM IP/URL and credentials must come from .env.

The core application must continue working if n8n is unavailable.

Provide n8n workflow documentation only.

Perform lightweight API tests.

Do not install or configure n8n.


--------------------



Perform the final project review.

---

## Final End-to-End Architecture Flow

```text
User
  │
  ▼
Frontend Portal
  │
  ▼
Authentication / Authorization
  │
  ▼
FastAPI Backend
  │
  ├──────────────┬──────────────┐
  ▼              ▼              ▼
Database        Redis           S3
(Metadata)    (Job Queue)    (CSV Data)
                 │
                 ▼
           Celery Worker
                 │
                 ▼
        Multiple CSV Files
                 │
                 ▼
      Shortcode + Date Filter
                 │
                 ▼
          Generated CSV
                 │
                 ▼
              ZIP File
                 │
                 ▼
         Local Job Storage
                 │
            ┌────┴────┐
            ▼         ▼
         Download    Email
```

## Optional AI / n8n Flow

```text
User
  │
  ▼
Frontend AI Assistant
  │
  ▼
Existing n8n VM
  │
  ▼
AI Agent
  │
  ▼
FastAPI APIs
  │
  ▼
Normal Extraction Flow
```

The existing n8n instance is external to the core application. It must not be installed or deployed as part of this project. AI/n8n must interact through secured FastAPI APIs and must never have unrestricted direct access to S3.
