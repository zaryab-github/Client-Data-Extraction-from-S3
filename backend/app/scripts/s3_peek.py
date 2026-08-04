"""Peek the first bytes of ONE daily CSV to reveal its header (read-only).

Fetches only a small leading byte-range (default 64 KB) via an S3 Range GET — it
does NOT download the whole (multi-hundred-MB) file. Used to confirm the CSV schema
(column names, delimiter, gzip-or-not) before implementing the Phase 4 extractor.

    python -m app.scripts.s3_peek --date 2023-09-01
    python -m app.scripts.s3_peek --key daily-jasminfiles-fatib/daily-data_2023-09-01.csv

Read-only: uses GetObject with a Range header. Never writes or deletes.
"""

from __future__ import annotations

import argparse
import sys
import zlib
from datetime import date, datetime

from app.config import settings
from app.services import s3_service


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Peek a daily CSV header (read-only).")
    p.add_argument("--date", type=_parse_date, help="File date (YYYY-MM-DD).")
    p.add_argument("--key", default=None, help="Full S3 key (overrides --date).")
    p.add_argument("--prefix", default=None, help="Override S3_PREFIX.")
    p.add_argument("--bytes", type=int, default=65536, help="Leading bytes to fetch.")
    p.add_argument("--lines", type=int, default=8, help="Lines to print.")
    args = p.parse_args(argv)

    if args.key:
        key = args.key
    elif args.date:
        prefix = settings.S3_PREFIX if args.prefix is None else args.prefix
        filename = s3_service._expand_template(settings.S3_FILE_TEMPLATE, args.date)
        key = s3_service._build_key(prefix, filename)
    else:
        print("Provide --date YYYY-MM-DD or --key <s3-key>")
        return 2

    print(f"Peeking s3://{settings.S3_BUCKET}/{key} (first {args.bytes} bytes)")
    print("-" * 60)

    try:
        resp = s3_service.get_client().get_object(
            Bucket=settings.S3_BUCKET, Key=key, Range=f"bytes=0-{args.bytes - 1}"
        )
        raw = resp["Body"].read()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 3

    gzipped = raw[:2] == b"\x1f\x8b"
    print(f"Detected format: {'GZIP (compressed)' if gzipped else 'plain text'}")

    if gzipped:
        try:
            text = zlib.decompressobj(zlib.MAX_WBITS | 16).decompress(raw).decode(
                "utf-8", "replace"
            )
        except Exception as exc:  # partial stream is expected
            print(f"(note: partial gzip decode — {type(exc).__name__})")
            text = ""
    else:
        text = raw.decode("utf-8", "replace")

    lines = text.splitlines()
    print(f"\nFirst {min(args.lines, len(lines))} line(s):")
    for i, line in enumerate(lines[: args.lines]):
        print(f"{i:>3}: {line}")

    if lines:
        header = lines[0]
        for delim, name in ((",", "comma"), ("\t", "tab"), (";", "semicolon"), ("|", "pipe")):
            if delim in header:
                cols = [c.strip() for c in header.split(delim)]
                print(f"\nLikely delimiter: {name}   columns: {len(cols)}")
                print(f"Column names: {cols}")
                has_sa = any(c.lower() == "source_addr" for c in cols)
                print(f"'source_addr' column present: {has_sa}")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
