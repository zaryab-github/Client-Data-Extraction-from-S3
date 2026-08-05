"""CSV extraction engine (Phase 4).

Given a validated request (shortcodes + date/time range), stream the relevant daily
CSV files from S3, keep only the rows whose shortcode column (default `source_addr`)
matches AND whose timestamp (default `created_at`) falls in the range, and write the
matching rows into one combined CSV — preserving all original columns.

Design goals:
  * CONSTANT MEMORY: files are streamed row-by-row from S3 and written incrementally
    to the output file. A multi-hundred-MB source file is never loaded into memory.
  * READ-ONLY source: only S3 GetObject/List — never modify or delete source files.
  * No Celery here (Phase 6). No Job ID / ZIP / storage here (Phase 5).

Rows whose shortcode matches but whose timestamp is missing/unparseable are KEPT
(and counted), per the agreed policy.

All column names / delimiter / format come from settings (.env).
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from app.config import settings
from app.services import s3_service

logger = logging.getLogger(__name__)

# Some fields (e.g. base64 short_message) can be long; raise the CSV field cap to a
# safe cross-platform value (< 2**31).
csv.field_size_limit(10_000_000)


class ExtractionError(Exception):
    """Raised for unrecoverable extraction problems (bad config, missing column)."""


@dataclass
class ExtractionRequest:
    shortcodes: list[str]
    date_from: datetime
    date_to: datetime
    # Optional: keep only rows whose destination_addr is one of these values.
    destinations: list[str] = field(default_factory=list)


@dataclass
class ExtractionStats:
    files_processed: int = 0
    files_missing: int = 0
    rows_scanned: int = 0
    rows_matched: int = 0
    bad_timestamp_rows: int = 0
    malformed_rows: int = 0
    source_keys: list[str] = field(default_factory=list)
    missing_dates: list[str] = field(default_factory=list)


# ── Streaming helpers ──────────────────────────────────────
class _S3RawStream(io.RawIOBase):
    """Adapt a botocore StreamingBody to a readable RawIOBase for buffering."""

    def __init__(self, body):
        self._body = body

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        chunk = self._body.read(len(b))
        if not chunk:
            return 0
        n = len(chunk)
        b[:n] = chunk
        return n

    def close(self) -> None:
        try:
            self._body.close()
        except Exception:  # noqa: BLE001
            pass
        super().close()


def _open_text_stream(body, compression: str, encoding: str = "utf-8"):
    raw = _S3RawStream(body)
    buffered = io.BufferedReader(raw)
    binary = gzip.GzipFile(fileobj=buffered) if compression == "gzip" else buffered
    return io.TextIOWrapper(binary, encoding=encoding, errors="replace", newline="")


def _to_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _parse_timestamp(raw: str, fmt: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        # Tolerate rows with/without the fractional-second part.
        base = raw.split(".", 1)[0]
        for f in (fmt.replace(".%f", ""), "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(base, f)
            except ValueError:
                continue
    return None


# ── Public API ─────────────────────────────────────────────
def run_extraction(
    request: ExtractionRequest,
    output_path: str,
    *,
    discovery: "s3_service.DiscoveryResult | None" = None,
    on_progress: Callable[[str], None] | None = None,
) -> ExtractionStats:
    """Extract matching rows for `request` into the CSV at `output_path`.

    `discovery` may be supplied to reuse a prior S3 file listing; otherwise the
    files are discovered here. `on_progress` receives human-readable milestone
    messages (used to stream a live job log to the UI).
    """
    def emit(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001 - logging must never break extraction
                pass

    shortcodes = {str(s).strip() for s in request.shortcodes if str(s).strip()}
    if not shortcodes:
        raise ExtractionError("No shortcodes provided.")
    if _to_naive(request.date_from) > _to_naive(request.date_to):
        raise ExtractionError("date_from must be on or before date_to.")

    destinations = {str(d).strip() for d in request.destinations if str(d).strip()}

    emit("Discovering source files in S3…")
    result = discovery or s3_service.discover_files(request.date_from, request.date_to)
    emit(
        f"Found {len(result.files)} file(s) to scan"
        + (f" · {len(result.missing_dates)} day(s) with no file" if result.missing_dates else "")
        + f". Filtering shortcode(s): {', '.join(sorted(shortcodes))}"
        + (f"; destination(s): {', '.join(sorted(destinations))}" if destinations else "")
        + "."
    )

    sc_col = settings.CSV_SHORTCODE_COLUMN
    dest_col = settings.CSV_DESTINATION_COLUMN
    delimiter = settings.CSV_DELIMITER
    ts_col = settings.CSV_TIMESTAMP_COLUMN or None
    ts_fmt = settings.CSV_TIMESTAMP_FORMAT or None
    compression = settings.CSV_COMPRESSION
    start = _to_naive(request.date_from)
    end = _to_naive(request.date_to)
    time_filter = bool(ts_col and ts_fmt)

    stats = ExtractionStats(
        files_missing=len(result.missing_dates),
        missing_dates=[d.isoformat() for d in result.missing_dates],
    )

    canonical_header: list[str] | None = None

    total_files = len(result.files)
    with open(output_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f, delimiter=delimiter)

        for idx, discovered in enumerate(result.files, 1):
            size_mb = f" ({discovered.size / 1048576:.0f} MB)" if discovered.size else ""
            emit(f"[{idx}/{total_files}] Reading {discovered.key}{size_mb}…")
            body = s3_service.get_object_stream(discovered.key)
            text = _open_text_stream(body, compression)
            last_emit = time.monotonic()
            try:
                reader = csv.reader(text, delimiter=delimiter)
                try:
                    header = next(reader)
                except StopIteration:
                    logger.warning("Empty CSV skipped: %s", discovered.key)
                    continue

                if sc_col not in header:
                    raise ExtractionError(
                        f"Shortcode column '{sc_col}' not found in {discovered.key} "
                        f"(header: {header[:10]}...)."
                    )
                sc_idx = header.index(sc_col)
                ts_idx = header.index(ts_col) if (time_filter and ts_col in header) else None
                if destinations and dest_col not in header:
                    raise ExtractionError(
                        f"Destination column '{dest_col}' not found in {discovered.key}."
                    )
                dest_idx = header.index(dest_col) if (destinations and dest_col in header) else None

                if canonical_header is None:
                    canonical_header = header
                    writer.writerow(header)

                stats.files_processed += 1
                stats.source_keys.append(discovered.key)

                for row in reader:
                    stats.rows_scanned += 1
                    if stats.rows_scanned % 200000 == 0:
                        now = time.monotonic()
                        if now - last_emit >= 2.0:
                            emit(
                                f"  …scanned {stats.rows_scanned:,} rows, "
                                f"matched {stats.rows_matched:,}"
                            )
                            last_emit = now
                    if sc_idx >= len(row):
                        stats.malformed_rows += 1
                        continue
                    if row[sc_idx].strip() not in shortcodes:
                        continue

                    if dest_idx is not None:
                        dval = row[dest_idx] if dest_idx < len(row) else ""
                        if dval.strip() not in destinations:
                            continue

                    if ts_idx is not None:
                        raw_ts = row[ts_idx] if ts_idx < len(row) else ""
                        ts = _parse_timestamp(raw_ts, ts_fmt)  # type: ignore[arg-type]
                        if ts is None:
                            stats.bad_timestamp_rows += 1
                            # Keep the row (agreed policy).
                        elif ts < start or ts > end:
                            continue

                    writer.writerow(row)
                    stats.rows_matched += 1
            finally:
                text.close()
            emit(f"[{idx}/{total_files}] Done {discovered.key} · matched {stats.rows_matched:,} so far")

    emit(
        f"Extraction complete: {stats.rows_matched:,} record(s) matched "
        f"from {stats.rows_scanned:,} scanned across {stats.files_processed} file(s)."
    )
    logger.info(
        "Extraction done: files=%d missing=%d scanned=%d matched=%d bad_ts=%d malformed=%d",
        stats.files_processed, stats.files_missing, stats.rows_scanned,
        stats.rows_matched, stats.bad_timestamp_rows, stats.malformed_rows,
    )
    return stats
