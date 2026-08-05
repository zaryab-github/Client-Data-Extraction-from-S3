"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { admin } from "@/lib/api-client";
import type { AdminUser } from "@/lib/auth";

const ROLES = ["admin", "analyst", "viewer"];

export default function AdminUsersPage() {
  const { user, loading } = useAuthGuard();
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("analyst");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = () => admin.listUsers().then(setUsers).catch(() => {});

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin") {
      router.replace("/dashboard");
      return;
    }
    refresh();
  }, [user, router]);

  function flash(ok: string | null, error: string | null) {
    setMsg(ok);
    setErr(error);
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    flash(null, null);
    try {
      await admin.createUser({ email: email.trim(), password, role });
      flash(`User ${email} created.`, null);
      setEmail("");
      setPassword("");
      refresh();
    } catch (e2) {
      flash(null, e2 instanceof Error ? e2.message : "Failed");
    }
  }

  async function changeRole(u: AdminUser, newRole: string) {
    flash(null, null);
    try {
      await admin.updateUser(u.id, { role: newRole });
      flash(`${u.email} is now ${newRole}.`, null);
      refresh();
    } catch (e2) {
      flash(null, e2 instanceof Error ? e2.message : "Failed");
    }
  }

  async function toggleActive(u: AdminUser) {
    flash(null, null);
    try {
      await admin.updateUser(u.id, { is_active: !u.is_active });
      flash(`${u.email} ${u.is_active ? "deactivated" : "activated"}.`, null);
      refresh();
    } catch (e2) {
      flash(null, e2 instanceof Error ? e2.message : "Failed");
    }
  }

  async function resetPassword(u: AdminUser) {
    const pw = window.prompt(`New password for ${u.email}:`);
    if (!pw) return;
    flash(null, null);
    try {
      await admin.updateUser(u.id, { password: pw });
      flash(`Password updated for ${u.email}.`, null);
    } catch (e2) {
      flash(null, e2 instanceof Error ? e2.message : "Failed");
    }
  }

  async function removeUser(u: AdminUser) {
    if (!window.confirm(`Delete ${u.email}? This cannot be undone.`)) return;
    flash(null, null);
    try {
      await admin.deleteUser(u.id);
      flash(`${u.email} deleted.`, null);
      refresh();
    } catch (e2) {
      flash(null, e2 instanceof Error ? e2.message : "Failed");
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
        <h1>Users</h1>
        {msg && <div className="notice success">{msg}</div>}
        {err && <div className="notice error">{err}</div>}

        <div className="card">
          <h2>Create user</h2>
          <form onSubmit={onCreate}>
            <div className="grid">
              <label className="field">
                <span>Email</span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </label>
              <label className="field">
                <span>Password</span>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </label>
              <label className="field">
                <span>Role</span>
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button className="btn" type="submit">
              Create user
            </button>
          </form>
        </div>

        <div className="card">
          <h2>All users ({users.length})</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>
                      <select
                        value={u.role}
                        onChange={(e) => changeRole(u, e.target.value)}
                        style={{ width: "auto" }}
                        disabled={u.id === user.id}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{u.is_active ? "active" : "inactive"}</td>
                    <td>{u.last_login_at?.slice(0, 19).replace("T", " ") ?? "—"}</td>
                    <td style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button className="btn secondary" onClick={() => toggleActive(u)} disabled={u.id === user.id}>
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button className="btn secondary" onClick={() => resetPassword(u)}>
                        Reset password
                      </button>
                      <button className="btn secondary" onClick={() => removeUser(u)} disabled={u.id === user.id}>
                        Delete
                      </button>
                    </td>
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
