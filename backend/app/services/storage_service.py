"""Local report storage.

Layout (root from .env REPORT_STORAGE_PATH):
    {REPORT_STORAGE_PATH}/jobs/{job_id}/
        extracted_data.csv
        {job_id}.zip
        metadata.json

Artifacts are built in a temp dir and atomically moved into place, so a partially
written report is never visible for download.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.config import settings

CSV_FILENAME = "extracted_data.csv"
METADATA_FILENAME = "metadata.json"


def jobs_root() -> Path:
    return Path(settings.REPORT_STORAGE_PATH) / "jobs"


def job_dir(job_id: str) -> Path:
    return jobs_root() / job_id


def zip_filename(job_id: str) -> str:
    return f"{job_id}.zip"


def new_temp_dir(job_id: str) -> Path:
    """Create and return a fresh temp working dir for a job."""
    tmp = jobs_root() / f".{job_id}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def publish(temp_dir: Path, job_id: str) -> Path:
    """Atomically move the temp dir to the final job dir; return the final path."""
    final = job_dir(job_id)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        shutil.rmtree(final)
    os.replace(str(temp_dir), str(final))
    return final


def delete_job_dir(job_id: str) -> bool:
    """Remove a job's stored artifacts. Returns True if something was removed."""
    final = job_dir(job_id)
    if final.exists():
        shutil.rmtree(final)
        return True
    return False


def cleanup_orphan_temp_dirs() -> int:
    """Remove leftover *.tmp working dirs (from crashes). Returns count removed."""
    root = jobs_root()
    if not root.exists():
        return 0
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.startswith(".") and entry.name.endswith(".tmp"):
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed
