"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { downloadReport, listJobs } from "@/lib/api-client";
import type { Job } from "@/lib/auth";

export default function HistoryPage() {
  const { user, loading } = useAuthGuard();
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    if (user) listJobs().then(setJobs).catch(() => {});
  }, [user]);

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
        <h1>Extraction history</h1>
        {jobs.length === 0 ? (
          <p className="muted">No jobs yet.</p>
        ) : (
          <div className="table-wrap">
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
                    <td>{j.status}</td>
                    <td>{j.requested_shortcodes.join(", ")}</td>
                    <td>{j.report ? j.report.csv_row_count.toLocaleString() : "—"}</td>
                    <td>{j.created_at?.slice(0, 19).replace("T", " ") ?? "—"}</td>
                    <td>
                      {j.status === "COMPLETED" && (
                        <button className="btn secondary" onClick={() => downloadReport(j.job_id)}>
                          Download
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
