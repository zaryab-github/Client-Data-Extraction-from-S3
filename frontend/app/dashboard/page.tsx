"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
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
    listJobs().then((j) => setJobs(j.slice(0, 5))).catch(() => {});
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
        <h1>Dashboard</h1>
        <p>
          <Link className="btn" href="/extract">
            + New extraction
          </Link>
        </p>

        <div className="card">
          <h2>Authorized shortcodes ({shortcodes.length})</h2>
          {shortcodes.length === 0 ? (
            <p className="muted">None yet — an admin must grant you access.</p>
          ) : (
            <p>{shortcodes.map((s) => s.code).join(", ")}</p>
          )}
        </div>

        <div className="card">
          <h2>Recent jobs</h2>
          {jobs.length === 0 ? (
            <p className="muted">No jobs yet.</p>
          ) : (
            <ul>
              {jobs.map((j) => (
                <li key={j.job_id}>
                  <Link href={`/jobs/${j.job_id}`}>{j.job_id}</Link> — {j.status}
                </li>
              ))}
            </ul>
          )}
          <p>
            <Link href="/history">View all history →</Link>
          </p>
        </div>
      </main>
    </>
  );
}
