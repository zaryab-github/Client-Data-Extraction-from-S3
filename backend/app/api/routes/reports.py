"""Report download routes (Phase 7).

- GET /reports/{job_id}/download → stream the ZIP (auth + ownership enforced).

The filesystem path is resolved server-side from the DB record and never accepted
from the client (path-traversal safe). Non-owners get 404; expired/cleaned reports
return 410.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core import rbac
from app.core.rbac import REPORT_DOWNLOAD
from app.db.models.job import ExtractionJob, ReportMetadata
from app.db.session import get_db
from app.services import audit_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{job_id}/download")
def download_report(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(require_permission(REPORT_DOWNLOAD))],
):
    job = db.scalar(select(ExtractionJob).where(ExtractionJob.job_id == job_id))
    if job is None or (job.user_id != user.id and not rbac.is_admin(user)):
        raise HTTPException(status_code=404, detail="Report not found.")

    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == job_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not available.")
    if not os.path.exists(report.zip_path):
        raise HTTPException(status_code=410, detail="Report has expired or been removed.")

    audit_service.record(
        db, audit_service.REPORT_DOWNLOAD, user=user, resource_type="report",
        resource_id=job_id, request=request,
    )

    # Friendly download filename from shortcodes + range.
    codes = "-".join(job.requested_shortcodes) if job.requested_shortcodes else "report"
    fname = f"{codes}_{job.date_from:%Y%m%d}_{job.date_to:%Y%m%d}.zip"
    return FileResponse(
        report.zip_path,
        media_type="application/zip",
        filename=fname,
        headers={"X-Checksum-SHA256": report.checksum_sha256 or ""},
    )
