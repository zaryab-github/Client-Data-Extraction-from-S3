"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import StatusBadge from "@/components/StatusBadge";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { getShortcodes, listJobs } from "@/lib/api-client";
import type { Job, Shortcode } from "@/lib/auth";

export default function DashboardPage() {
  const { user, loading } = useAuthGuard();
  const [shortcodes, setShortcodes] = useState<Shortcode[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    if (!user) return;
    getShortcodes().then(setShortcodes).catch(() => {});
    listJobs().then(setJobs).catch(() => {});
  }, [user]);

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  const completed = jobs.filter((j) => j.status === "COMPLETED").length;
  const running = jobs.filter((j) => ["PENDING", "PROCESSING"].includes(j.status)).length;

  return (
    <>
      <Nav user={user} />
      <main>
        <div className="page-head">
          <h1 style={{ margin: 0 }}>Welcome back</h1>
          <Link className="btn" href="/extract">
            + New extraction
          </Link>
        </div>

        <div className="grid" style={{ marginTop: 16 }}>
          <div className="stat">
            <div className="label">Authorized shortcodes</div>
            <div className="value">{shortcodes.length}</div>
          </div>
          <div className="stat">
            <div className="label">Total jobs</div>
            <div className="value">{jobs.length}</div>
          </div>
          <div className="stat">
            <div className="label">Completed</div>
            <div className="value">{completed}</div>
          </div>
          <div className="stat">
            <div className="label">In progress</div>
            <div className="value">{running}</div>
          </div>
        </div>

        <div className="card">
          <h2>Your shortcodes</h2>
          {shortcodes.length === 0 ? (
            <p className="muted">None yet — an admin must grant you access.</p>
          ) : (
            <p>{shortcodes.map((s) => s.code).join(", ")}</p>
          )}
        </div>

        <div className="card">
          <div className="page-head">
            <h2 style={{ margin: 0 }}>Recent jobs</h2>
            <Link href="/history">View all →</Link>
          </div>
          {jobs.length === 0 ? (
            <p className="muted">No jobs yet.</p>
          ) : (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Status</th>
                    <th>Shortcodes</th>
                    <th>Records</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.slice(0, 6).map((j) => (
                    <tr key={j.job_id}>
                      <td>
                        <Link href={`/jobs/${j.job_id}`}>{j.job_id}</Link>
                      </td>
                      <td>
                        <StatusBadge status={j.status} />
                      </td>
                      <td>{j.requested_shortcodes.join(", ")}</td>
                      <td>{j.report ? j.report.csv_row_count.toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
