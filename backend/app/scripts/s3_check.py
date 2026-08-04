"""Live S3 connectivity + discovery check (Phase 3).

Run on a host whose .env has the real AWS read-only credentials:

    python -m app.scripts.s3_check --from 2023-09-01 --to 2023-09-05
    python -m app.scripts.s3_check --from 2023-09-01 --to 2023-09-05 --prefix daily-jasminfiles-fatib

It verifies bucket reachability and lists which daily files exist / are missing in
the range. It performs READ-ONLY operations only (HeadBucket / List / Head).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from app.config import settings
from app.services import s3_service


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check S3 connectivity and file discovery.")
    parser.add_argument("--from", dest="date_from", type=_parse_date,
                        default=date.today() - timedelta(days=3))
    parser.add_argument("--to", dest="date_to", type=_parse_date, default=date.today())
    parser.add_argument("--prefix", default=None, help="Override S3_PREFIX for this check.")
    parser.add_argument("--mode", default=None, choices=["list", "template"])
    args = parser.parse_args(argv)

    print(f"Bucket: {settings.S3_BUCKET or '(not set!)'}")
    print(f"Region: {settings.AWS_REGION or '(not set!)'}")
    print(f"Prefix: {args.prefix if args.prefix is not None else settings.S3_PREFIX}")
    print(f"Range : {args.date_from} .. {args.date_to}")
    print("-" * 50)

    try:
        s3_service.check_connection()
        print("Connection: OK (HeadBucket succeeded)")
    except Exception as exc:  # noqa: BLE001
        print(f"Connection FAILED: {type(exc).__name__}: {exc}")
        return 2

    try:
        result = s3_service.discover_files(
            args.date_from, args.date_to, prefix=args.prefix, mode=args.mode
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Discovery FAILED: {type(exc).__name__}: {exc}")
        return 3

    print(f"\nFound {result.found_count} file(s):")
    for f in result.files:
        size = f"{f.size:,} bytes" if f.size is not None else "?"
        print(f"  {f.file_date}  {f.key}  ({size})")
    if result.missing_dates:
        print(f"\nMissing {len(result.missing_dates)} day(s): "
              + ", ".join(d.isoformat() for d in result.missing_dates))
    print("\nOK — S3 read-only discovery works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
