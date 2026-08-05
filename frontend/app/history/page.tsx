"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import StatusBadge from "@/components/StatusBadge";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { downloadReport, listJobs } from "@/lib/api-client";
import type { Job } from "@/lib/auth";

export default function HistoryPage() {
  const { user, loading } = useAuthGuard();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (user) listJobs(filter || undefined).then(setJobs).catch(() => {});
  }, [user, filter]);

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
        <div className="page-head">
          <h1 style={{ margin: 0 }}>Extraction history</h1>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ width: "auto" }}
          >
            <option value="">All statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="PROCESSING">Processing</option>
            <option value="PENDING">Pending</option>
            <option value="FAILED">Failed</option>
            <option value="EXPIRED">Expired</option>
          </select>
        </div>

        {jobs.length === 0 ? (
          <div className="card">
            <p className="muted">No jobs yet. Start one from the Extract tab.</p>
          </div>
        ) : (
          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Status</th>
                  <th>Shortcodes</th>
                  <th>Records</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.job_id}>
                    <td>
                      <Link href={`/jobs/${j.job_id}`}>{j.job_id}</Link>
                    </td>
                    <td>
                      <StatusBadge status={j.status} />
                    </td>
                    <td>{j.requested_shortcodes.join(", ")}</td>
                    <td>{j.report ? j.report.csv_row_count.toLocaleString() : "—"}</td>
                    <td>{j.created_at?.slice(0, 19).replace("T", " ") ?? "—"}</td>
                    <td>
                      {j.status === "COMPLETED" && (
                        <button className="btn secondary" onClick={() => downloadReport(j.job_id)}>
                          ⬇ Download
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  );
}
