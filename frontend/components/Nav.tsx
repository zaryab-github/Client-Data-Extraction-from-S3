"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api-client";
import type { CurrentUser } from "@/lib/auth";

export default function Nav({ user }: { user: CurrentUser }) {
  const router = useRouter();
  const isAdmin = user.role === "admin";

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <nav className="topnav">
      <div>
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/extract">Extract</Link>
        <Link href="/history">History</Link>
        {isAdmin && <Link href="/admin/shortcodes">Shortcodes</Link>}
        {isAdmin && <Link href="/admin/users">Users</Link>}
        {isAdmin && <Link href="/admin/audit">Audit</Link>}
      </div>
      <div>
        <span className="muted" style={{ marginRight: 12 }}>
          {user.email} ({user.role})
        </span>
        <button className="btn secondary" onClick={onLogout}>
          Log out
        </button>
      </div>
    </nav>
  );
}
