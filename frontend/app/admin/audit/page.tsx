"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { admin } from "@/lib/api-client";
import type { AuditEntry } from "@/lib/auth";

export default function AdminAuditPage() {
  const { user, loading } = useAuthGuard();
  const router = useRouter();
  const [rows, setRows] = useState<AuditEntry[]>([]);

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin") {
      router.replace("/dashboard");
      return;
    }
    admin.listAudit().then(setRows).catch(() => {});
  }, [user, router]);

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
        <h1>Audit log</h1>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Resource</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.created_at.slice(0, 19).replace("T", " ")}</td>
                  <td>{r.user_email ?? "—"}</td>
                  <td>{r.action}</td>
                  <td>
                    {r.resource_type ?? ""} {r.resource_id ?? ""}
                  </td>
                  <td>{r.ip_address ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
