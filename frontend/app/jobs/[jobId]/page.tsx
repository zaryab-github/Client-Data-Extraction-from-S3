"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { downloadReport, getJob } from "@/lib/api-client";
import { config } from "@/lib/config";
import type { Job } from "@/lib/auth";

const TERMINAL = ["COMPLETED", "FAILED", "EXPIRED"];

export default function JobStatusPage() {
  const { user, loading } = useAuthGuard();
  const params = useParams();
  const jobId = String(params.jobId);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const j = await getJob(jobId);
        if (!active) return;
        setJob(j);
        if (!TERMINAL.includes(j.status)) {
          timer = setTimeout(poll, config.jobPollIntervalMs);
        }
      } catch {
        if (active) setErr("Could not load this job.");
      }
    };
    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [user, jobId]);

  async function onDownload() {
    try {
      await downloadReport(jobId);
    } catch {
      setErr("Download failed (the report may have expired).");
    }
  }

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <>
      <Nav user={user} />
      <main>
        <h1>Job {jobId}</h1>
        {err && <p className="err">{err}</p>}
        {!job ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <p>
              Status: <strong>{job.status}</strong>
            </p>
            {!TERMINAL.includes(job.status) && (
              <p className="muted">Processing… this page updates automatically.</p>
            )}
            <div className="card">
              <ul>
                <li>Shortcodes: {job.requested_shortcodes.join(", ")}</li>
                <li>Range: {job.date_from} → {job.date_to}</li>
                <li>Created: {job.created_at ?? "—"}</li>
                <li>Finished: {job.finished_at ?? "—"}</li>
              </ul>
            </div>

            {job.status === "FAILED" && <p className="err">Error: {job.error_message}</p>}

            {job.status === "COMPLETED" && job.report && (
              <div className="card">
                <h2>Report</h2>
                <ul>
                  <li>Records extracted: {job.report.csv_row_count.toLocaleString()}</li>
                  <li>Rows scanned: {job.report.rows_scanned.toLocaleString()}</li>
                  <li>
                    Files processed: {job.report.source_file_count} (missing{" "}
                    {job.report.missing_file_count})
                  </li>
                  <li>ZIP size: {(job.report.zip_size_bytes / 1048576).toFixed(2)} MB</li>
                  <li>Expires: {job.report.expires_at ?? "—"}</li>
                </ul>
                <button className="btn" onClick={onDownload}>
                  Download ZIP
                </button>{" "}
                <button className="btn secondary" disabled title="Available in Phase 8">
                  Email report
                </button>
              </div>
            )}

            {job.status === "EXPIRED" && (
              <p className="muted">This report has passed its retention window and was removed.</p>
            )}
          </>
        )}
      </main>
    </>
  );
}
