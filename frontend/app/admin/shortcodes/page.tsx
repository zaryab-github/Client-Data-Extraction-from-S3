"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { admin } from "@/lib/api-client";
import type { AdminShortcode, AdminUser } from "@/lib/auth";

export default function AdminShortcodesPage() {
  const { user, loading } = useAuthGuard();
  const router = useRouter();
  const [shortcodes, setShortcodes] = useState<AdminShortcode[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // create form
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [prefix, setPrefix] = useState("");

  // grant form
  const [grantUser, setGrantUser] = useState("");
  const [grantCodes, setGrantCodes] = useState("");

  const refresh = () => {
    admin.listShortcodes().then(setShortcodes).catch(() => {});
    admin.listUsers().then(setUsers).catch(() => {});
  };

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin") {
      router.replace("/dashboard");
      return;
    }
    refresh();
  }, [user, router]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      await admin.createShortcode({ code: code.trim(), name: name.trim() || `Client ${code}`, s3_prefix: prefix || undefined });
      setMsg(`Shortcode ${code} registered.`);
      setCode("");
      setName("");
      setPrefix("");
      refresh();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Failed");
    }
  }

  async function onGrant(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    const codes = grantCodes.split(",").map((c) => c.trim()).filter(Boolean);
    try {
      const res = await admin.grant(grantUser, codes);
      setMsg(`Granted: ${res.granted.join(", ") || "(already granted)"}`);
      setGrantCodes("");
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Failed");
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
        <h1>Shortcodes</h1>
        {msg && <p className="ok">{msg}</p>}
        {err && <p className="err">{err}</p>}

        <div className="card">
          <h2>Register a shortcode</h2>
          <form onSubmit={onCreate}>
            <label className="field">
              <span>Code (matches source_addr, e.g. 8890)</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} required />
            </label>
            <label className="field">
              <span>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="field">
              <span>S3 prefix override (optional)</span>
              <input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="daily-jasminfiles-fatib" />
            </label>
            <button className="btn" type="submit">
              Register
            </button>
          </form>
        </div>

        <div className="card">
          <h2>Grant access to a user</h2>
          <form onSubmit={onGrant}>
            <label className="field">
              <span>User</span>
              <select value={grantUser} onChange={(e) => setGrantUser(e.target.value)} required>
                <option value="">Select a user…</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.email} ({u.role})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Shortcode codes (comma-separated)</span>
              <input value={grantCodes} onChange={(e) => setGrantCodes(e.target.value)} placeholder="8890, 8981" required />
            </label>
            <button className="btn" type="submit">
              Grant
            </button>
          </form>
        </div>

        <div className="card">
          <h2>All shortcodes ({shortcodes.length})</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>S3 prefix</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {shortcodes.map((s) => (
                  <tr key={s.id}>
                    <td>{s.code}</td>
                    <td>{s.name}</td>
                    <td>{s.s3_prefix ?? "(default)"}</td>
                    <td>{s.is_active ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </>
  );
}
