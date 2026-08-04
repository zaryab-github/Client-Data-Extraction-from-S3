"""Live extraction check (Phase 4).

Streams the real daily files from S3 and extracts matching rows for one or more
shortcodes over a date/time range — writing to a temp/output CSV and printing stats.
Use it to validate the engine against real (large) files and confirm streaming works.

    python -m app.scripts.extract_check --shortcodes 8990 --from 2023-09-01 --to 2023-09-01
    python -m app.scripts.extract_check --shortcodes 8990,1234 \
        --from "2023-09-01 09:00:00" --to "2023-09-01 17:00:00" --out /tmp/8990.csv

Read-only against S3. Writes only the local output CSV.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime

from app.services.extraction_service import ExtractionRequest, run_extraction


def _parse_dt(s: str, *, end: bool = False) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d" and end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Invalid datetime: {s!r} (use YYYY-MM-DD or 'YYYY-MM-DD HH:MM:SS')")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Live extraction check against real S3 files.")
    p.add_argument("--shortcodes", required=True, help="Comma-separated source_addr values, e.g. 8990,1234")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--out", default=None, help="Output CSV path (default: a temp file).")
    args = p.parse_args(argv)

    shortcodes = [s.strip() for s in args.shortcodes.split(",") if s.strip()]
    date_from = _parse_dt(args.date_from)
    date_to = _parse_dt(args.date_to, end=True)
    out_path = args.out or os.path.join(tempfile.gettempdir(), "extract_check.csv")

    print(f"Shortcodes: {shortcodes}")
    print(f"Range     : {date_from} .. {date_to}")
    print(f"Output    : {out_path}")
    print("-" * 60)

    started = time.time()
    try:
        stats = run_extraction(
            ExtractionRequest(shortcodes=shortcodes, date_from=date_from, date_to=date_to),
            out_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 3
    elapsed = time.time() - started

    size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    print(f"Files processed : {stats.files_processed}")
    print(f"Files missing   : {stats.files_missing} {stats.missing_dates or ''}")
    print(f"Rows scanned    : {stats.rows_scanned:,}")
    print(f"Rows matched    : {stats.rows_matched:,}")
    print(f"Bad timestamps  : {stats.bad_timestamp_rows:,} (kept)")
    print(f"Malformed rows  : {stats.malformed_rows:,}")
    print(f"Output size     : {size:,} bytes")
    print(f"Elapsed         : {elapsed:.1f}s")
    print("\nOK — extraction engine works on real data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
