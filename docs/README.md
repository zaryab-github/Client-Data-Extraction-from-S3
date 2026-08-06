# Documentation

Everything for the Client Data Extraction & Delivery System. Deployment quickstart is
in the root [README](../README.md); the details live here.

| Document | What it covers |
|----------|----------------|
| [architecture.md](architecture.md) | Complete design & end-to-end flow — components, S3/extraction model, request lifecycle, security model, data stored. |
| [development_phases.md](development_phases.md) | The phase-by-phase build plan (as authored). |
| [features.md](features.md) | What's built, what's planned, operational CLIs, behaviour notes. |
| [deployment.md](deployment.md) | Full deploy runbook — verify, CLIs, redeploy, backups, scaling, optional TLS, local dev. |
| [operations.md](operations.md) | **Day-2 runbook** — check job status/details, container / log / DB management, troubleshooting quick reference. |
| [docker-compose.md](docker-compose.md) | The seven containers, what each does, ports, volumes, connections. |
| [env-reference.md](env-reference.md) | Every `.env` value and how to obtain it. |
| [gmail-drive-setup.md](gmail-drive-setup.md) | Getting the Gmail OAuth2 refresh token with the Gmail + Drive scopes. |
| [security-review.md](security-review.md) | Security review against the 17-point checklist + hardening + IAM policy. |

## The golden rules

1. All configurable values come from `.env` — no hardcoded secrets/URLs/credentials.
2. **S3 is read-only** — source files are never modified or deleted.
3. The database stores **application metadata only** — never client CSV data.
4. The backend independently enforces authentication and every permission.
5. Runs on a **local IP over HTTP** behind nginx (optional self-signed TLS).
