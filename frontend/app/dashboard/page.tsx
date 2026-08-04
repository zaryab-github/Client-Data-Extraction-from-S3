"use client";

// Protected dashboard. Client-side guard: if the user isn't authenticated (or the
// token is invalid/expired), redirect to /login. The backend independently enforces
// auth on every API call — this guard is only for UX.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, getShortcodes, logout } from "@/lib/api-client";
import type { CurrentUser, Shortcode } from "@/lib/auth";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [shortcodes, setShortcodes] = useState<Shortcode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const me = await getMe();
        const codes = await getShortcodes();
        if (!active) return;
        setUser(me);
        setShortcodes(codes);
      } catch {
        router.replace("/login");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  if (loading) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (!user) return null;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Dashboard</h1>
        <button onClick={onLogout} style={logoutStyle}>
          Log out
        </button>
      </div>

      <section>
        <h2>Signed in as</h2>
        <ul>
          <li>Email: <code>{user.email}</code></li>
          <li>Role: <code>{user.role}</code></li>
          <li>Permissions: <code>{user.permissions.join(", ") || "(none)"}</code></li>
        </ul>
      </section>

      <section>
        <h2>Authorized shortcodes</h2>
        {shortcodes.length === 0 ? (
          <p className="muted">You have no authorized shortcodes yet.</p>
        ) : (
          <ul>
            {shortcodes.map((s) => (
              <li key={s.id}>
                <code>{s.code}</code> — {s.name}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="muted">
        Extraction, job status, history, and admin screens are added in later phases.
      </p>
    </main>
  );
}

const logoutStyle: React.CSSProperties = {
  padding: "8px 14px",
  borderRadius: 6,
  border: "1px solid #334155",
  background: "transparent",
  color: "inherit",
  cursor: "pointer",
};
