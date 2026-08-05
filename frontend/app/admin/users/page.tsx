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

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      await admin.createUser({ email: email.trim(), password, role });
      setMsg(`User ${email} created.`);
      setEmail("");
      setPassword("");
      refresh();
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
        <h1>Users</h1>
        {msg && <p className="ok">{msg}</p>}
        {err && <p className="err">{err}</p>}

        <div className="card">
          <h2>Create user</h2>
          <form onSubmit={onCreate}>
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
            <button className="btn" type="submit">
              Create
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
                  <th>Active</th>
                  <th>Last login</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>{u.role}</td>
                    <td>{u.is_active ? "yes" : "no"}</td>
                    <td>{u.last_login_at?.slice(0, 19).replace("T", " ") ?? "—"}</td>
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
