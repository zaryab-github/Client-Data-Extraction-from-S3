"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Nav from "@/components/Nav";
import StatusBadge from "@/components/StatusBadge";
import { useAuthGuard } from "@/lib/useAuthGuard";
import {
  downloadReport,
  emailReport,
  getEmailDeliveries,
  getJob,
  getJobLogs,
} from "@/lib/api-client";
import { config } from "@/lib/config";
import type { EmailDelivery, Job, JobLog } from "@/lib/auth";

const TERMINAL = ["COMPLETED", "FAILED", "EXPIRED"];

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default function JobStatusPage() {
  const { user, loading } = useAuthGuard();
  const params = useParams();
  const jobId = String(params.jobId);
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [emails, setEmails] = useState<EmailDelivery[]>([]);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const lastLogIdRef = useRef(0);

  const pullLogs = useCallback(async () => {
    try {
      const next = await getJobLogs(jobId, lastLogIdRef.current);
      if (next.length) {
        lastLogIdRef.current = next[next.length - 1].id;
        setLogs((prev) => [...prev, ...next]);
      }
    } catch {
      /* ignore transient log errors */
    }
  }, [jobId]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const j = await getJob(jobId);
        if (!active) return;
        setJob(j);
        await pullLogs();
        if (!TERMINAL.includes(j.status)) {
          timer = setTimeout(poll, config.jobPollIntervalMs);
        } else {
          // catch any trailing COMPLETED/FAILED log line written just after status
          setTimeout(pullLogs, 1500);
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
  }, [user, jobId, pullLogs]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  async function onDownload() {
    setDownloading(true);
    try {
      await downloadReport(jobId);
    } catch {
      setErr("Download failed (the report may have expired).");
    } finally {
      setDownloading(false);
    }
  }

  async function loadEmails() {
    try {
      setEmails(await getEmailDeliveries(jobId));
    } catch {
      /* email may not be enabled / no permission — ignore */
    }
  }

  async function onEmail() {
    const to = window.prompt("Send report to (email):", user?.email ?? "");
    if (!to) return;
    setEmailMsg(null);
    try {
      await emailReport(jobId, to);
      setEmailMsg(`Queued email to ${to}. Watch the live log below for progress.`);
      // Poll logs + delivery status until the email finishes (or ~90s).
      for (let i = 0; i < 45; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        await pullLogs();
        let deliveries: EmailDelivery[] = [];
        try {
          deliveries = await getEmailDeliveries(jobId);
        } catch {
          /* ignore */
        }
        setEmails(deliveries);
        const latest = deliveries[0];
        if (latest && (latest.status === "SENT" || latest.status === "FAILED")) break;
      }
    } catch (e) {
      setEmailMsg(e instanceof Error ? e.message : "Failed to queue email.");
    }
  }

  useEffect(() => {
    if (job?.status === "COMPLETED") loadEmails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  const r = job?.report;
  const noSourceFiles = job?.status === "COMPLETED" && r && r.source_file_count === 0;
  const running = job != null && !TERMINAL.includes(job.status);

  return (
    <>
      <Nav user={user} />
      <main>
        <div className="page-head">
          <h1 style={{ margin: 0 }}>
            Job <code>{jobId}</code>
          </h1>
          {job && <StatusBadge status={job.status} />}
        </div>

        {err && <div className="notice error">{err}</div>}

        {!job ? (
          <p className="muted">
            <span className="spinner" /> Loading…
          </p>
        ) : (
          <>
            {running && (
              <div className="notice warn">
                <span className="spinner" /> Processing in the background — status and logs update
                automatically.
              </div>
            )}

            <div className="card">
              <h2>Request</h2>
              <div className="grid">
                <Stat label="Shortcodes" value={job.requested_shortcodes.join(", ")} />
                <Stat label="From" value={job.date_from.replace("T", " ").replace("Z", "")} />
                <Stat label="To" value={job.date_to.replace("T", " ").replace("Z", "")} />
                {job.destination_addrs && job.destination_addrs.length > 0 && (
                  <Stat label="Destination filter" value={job.destination_addrs.join(", ")} />
                )}
              </div>
            </div>

            {/* Live log console */}
            <div className="card">
              <h2>Live log{running && <span className="muted"> · updating…</span>}</h2>
              <div className="console">
                {logs.length === 0 ? (
                  <span className="muted">Waiting for logs…</span>
                ) : (
                  logs.map((l) => (
                    <div key={l.id} className={`logline${l.level === "ERROR" ? " log-err" : ""}`}>
                      <span className="log-time">{l.created_at.slice(11, 19)}</span>
                      {l.message}
                    </div>
                  ))
                )}
                <div ref={logEndRef} />
              </div>
            </div>

            {job.status === "FAILED" && (
              <div className="notice error">
                <strong>Extraction failed.</strong>
                <br />
                {job.error_message}
              </div>
            )}

            {noSourceFiles && (
              <div className="notice warn">
                <strong>No source files found for this date range.</strong> The daily CSV files
                for these dates don&apos;t exist in S3 ({r!.missing_file_count} missing), so nothing
                could be extracted. Double-check the dates, or ask an admin to confirm the data
                coverage for this period.
              </div>
            )}

            {job.status === "COMPLETED" && r && !noSourceFiles && (
              <div className="card">
                <h2>Report</h2>
                <div className="grid">
                  <Stat label="Records extracted" value={r.csv_row_count.toLocaleString()} />
                  <Stat label="Rows scanned" value={r.rows_scanned.toLocaleString()} />
                  <Stat label="Files processed" value={r.source_file_count} />
                  <Stat label="Missing days" value={r.missing_file_count} />
                  <Stat label="ZIP size" value={`${(r.zip_size_bytes / 1048576).toFixed(2)} MB`} />
                </div>
                <p className="muted" style={{ marginTop: 12 }}>
                  Expires {r.expires_at?.slice(0, 10) ?? "—"}
                </p>

                {r.source_files && r.source_files.length > 0 && (
                  <details style={{ margin: "8px 0 16px" }}>
                    <summary style={{ cursor: "pointer" }}>
                      Files scanned ({r.source_files.length})
                    </summary>
                    <ul style={{ marginTop: 8 }}>
                      {r.source_files.map((f) => (
                        <li key={f}>
                          <code>{f}</code>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                  <button className="btn" onClick={onDownload} disabled={downloading}>
                    {downloading ? "Preparing…" : "⬇ Download ZIP"}
                  </button>
                  <button className="btn secondary" onClick={onEmail}>
                    ✉ Email report
                  </button>
                </div>

                {emailMsg && <p className="muted" style={{ marginTop: 10 }}>{emailMsg}</p>}
                {emails.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <strong>Email deliveries</strong>
                    <ul>
                      {emails.map((e) => (
                        <li key={e.id}>
                          {e.recipient} — <strong>{e.status}</strong>
                          {e.method ? ` (${e.method})` : ""}
                          {e.error ? ` — ${e.error}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </>
  );
}
