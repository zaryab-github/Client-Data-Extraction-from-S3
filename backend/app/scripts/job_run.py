"""Live end-to-end job run (Phase 5).

Creates a real extraction job for a user, runs it synchronously (extract → zip →
store → record metadata), and prints the result. Useful to validate the full
storage/reporting pipeline on the server against real S3 data.

    python -m app.scripts.job_run --user zaryab.ansari@eocean.net \
        --shortcodes 8890 --from 2023-09-01 --to 2023-09-01

Read-only against S3; writes report artifacts to REPORT_STORAGE_PATH.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from sqlalchemy import select

from app.db.models.user import User
from app.db.session import get_session_factory
from app.services import job_service
from app.services.extraction_service import ExtractionRequest


def _parse_dt(s: str, *, end: bool = False) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d" and end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid datetime: {s!r}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run a real extraction job.")
    p.add_argument("--user", required=True, help="Email of the requesting user.")
    p.add_argument("--shortcodes", required=True, help="Comma-separated source_addr values.")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    args = p.parse_args(argv)

    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.email == args.user))
        if user is None:
            print(f"User not found: {args.user}")
            return 2

        request = ExtractionRequest(
            shortcodes=[s.strip() for s in args.shortcodes.split(",") if s.strip()],
            date_from=_parse_dt(args.date_from),
            date_to=_parse_dt(args.date_to, end=True),
        )
        job = job_service.create_and_run(db, user, request)

        print(f"Job ID : {job.job_id}")
        print(f"Status : {job.status}")
        if job.error_message:
            print(f"Error  : {job.error_message}")
            return 3

        from app.services import storage_service
        d = storage_service.job_dir(job.job_id)
        print(f"Dir    : {d}")
        print(f"Files  : {[f.name for f in d.iterdir()]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
