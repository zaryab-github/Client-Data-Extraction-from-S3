"""Application configuration.

Every configurable value is loaded from the environment (``.env``). Nothing
sensitive is hardcoded here — no secrets, credentials, URLs, IPs, AWS settings,
S3 bucket names, database URLs, or Redis URLs.

Secret/connection values default to empty strings so the module always imports;
their presence is validated explicitly via :meth:`Settings.require` at startup,
which fails fast with a clear message if something required is missing.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────
    APP_ENV: str = "development"           # development | staging | production
    APP_NAME: str = "client-data-extraction"
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: str = ""         # comma-separated; see cors_origins property
    LOG_LEVEL: str = "INFO"
    # Interactive API docs (/docs, /redoc, /openapi.json). Disable in production if
    # you don't want the schema publicly reachable.
    ENABLE_API_DOCS: bool = True

    # ── Security / Auth (Phase 2 uses these; declared now, from .env only) ──
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_HASH_SCHEME: str = "argon2"
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # Refresh-token cookie. Over plain HTTP (IP deploy) COOKIE_SECURE must be False,
    # or the browser won't send the cookie. Set True once TLS is in front.
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # First admin + optional demo data, created by `python -m app.scripts.seed`.
    FIRST_ADMIN_EMAIL: str = ""
    FIRST_ADMIN_PASSWORD: str = ""
    SEED_DEMO_DATA: bool = False

    # ── Database (metadata only — never client CSV data) ───
    DATABASE_URL: str = ""

    # ── Redis / Celery ─────────────────────────────────────
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""            # falls back to REDIS_URL if empty
    CELERY_RESULT_BACKEND: str = ""        # falls back to REDIS_URL if empty
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3000
    CELERY_TASK_TIME_LIMIT: int = 21600
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_MAX_RETRIES: int = 3
    # How often Celery beat runs the retention cleanup (seconds; default daily).
    RETENTION_CLEANUP_INTERVAL_SECONDS: int = 86400

    # ── AWS / S3 (read-only source; Phase 4) ───────────────
    AWS_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_PREFIX: str = ""
    S3_FILE_TEMPLATE: str = "daily-data_{yyyy}-{mm}-{dd}.csv"
    S3_DISCOVERY_MODE: str = "list"        # list | template
    S3_MAX_RETRIES: int = 5

    # ── CSV extraction (Phase 4) ───────────────────────────
    CSV_SHORTCODE_COLUMN: str = "source_addr"
    # Optional additional filter column (e.g. destination_addr / MSISDN).
    CSV_DESTINATION_COLUMN: str = "destination_addr"
    CSV_DELIMITER: str = ","
    CSV_HAS_HEADER: bool = True
    CSV_COMPRESSION: str = "none"          # none | gzip
    CSV_TIMESTAMP_COLUMN: str = ""
    CSV_TIMESTAMP_FORMAT: str = ""
    EXTRACTION_PARALLEL_FILES: bool = True

    # ── Jobs / storage / retention (Phase 5-8) ─────────────
    JOB_ID_STRATEGY: str = "ext_seq"       # ext_seq (EXT-YYYYMMDD-NNNNNN) | uuid4
    MAX_RANGE_DAYS: int = 92
    REPORT_STORAGE_PATH: str = "./storage"
    REPORT_RETENTION_DAYS: int = 30
    ZIP_COMPRESSION_LEVEL: int = 6

    # ── Email (Phase 8) ────────────────────────────────────
    EMAIL_ENABLED: bool = False
    EMAIL_PROVIDER: str = "gmail"          # gmail | smtp | ses
    EMAIL_FROM_ADDRESS: str = ""           # used by smtp/ses (gmail uses GMAIL_SENDER)
    EMAIL_MAX_ATTACHMENT_BYTES: int = 10_485_760
    DOWNLOAD_LINK_EXPIRE_MINUTES: int = 60
    # Public base URL of THIS API (for building download links inside emails),
    # e.g. http://192.168.255.171/api/v1
    PUBLIC_API_BASE_URL: str = ""

    # Gmail OAuth2 (EMAIL_PROVIDER=gmail)
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    GMAIL_TOKEN_URI: str = "https://oauth2.googleapis.com/token"
    GMAIL_SENDER: str = ""
    # Optional Google Drive folder id to upload large reports into (else My Drive root).
    # The OAuth token must include the drive.file scope for uploads to work.
    GDRIVE_FOLDER_ID: str = ""

    # SMTP (EMAIL_PROVIDER=smtp)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    # ── n8n integration (external; Phase 10) ───────────────
    N8N_BASE_URL: str = ""
    N8N_SERVICE_TOKEN: str = ""
    N8N_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_SECRET: str = ""

    # ── Derived / helpers ──────────────────────────────────
    @property
    def cors_origins(self) -> list[str]:
        """Parse the comma-separated CORS origins into a list."""
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    def require(self) -> None:
        """Fail fast if a required configuration value is missing.

        Called at application startup. Keeping validation here (rather than at
        import time) lets tooling and tests import ``Settings`` freely.
        """
        missing: list[str] = []
        required = {
            "JWT_SECRET": self.JWT_SECRET,
            "DATABASE_URL": self.DATABASE_URL,
            "REDIS_URL": self.REDIS_URL,
        }
        for name, value in required.items():
            if not value:
                missing.append(name)
        if not self.celery_broker:
            missing.append("CELERY_BROKER_URL (or REDIS_URL)")
        if missing:
            raise RuntimeError(
                "Missing required environment configuration: "
                + ", ".join(missing)
                + ". Set them in your .env (see backend/.env.example)."
            )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Convenient module-level accessor.
settings = get_settings()
