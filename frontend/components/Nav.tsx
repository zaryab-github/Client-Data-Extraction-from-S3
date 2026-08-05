"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api-client";
import type { CurrentUser } from "@/lib/auth";

const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/extract", label: "Extract" },
  { href: "/history", label: "History" },
];
const ADMIN_TABS = [
  { href: "/admin/shortcodes", label: "Shortcodes" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/audit", label: "Audit" },
];

export default function Nav({ user }: { user: CurrentUser }) {
  const router = useRouter();
  const pathname = usePathname();
  const tabs = user.role === "admin" ? [...TABS, ...ADMIN_TABS] : TABS;

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <nav className="topnav">
      <div className="nav-tabs">
        <span className="nav-brand">Extraction</span>
        {tabs.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={pathname?.startsWith(t.href) ? "active" : ""}
          >
            {t.label}
          </Link>
        ))}
      </div>
      <div className="nav-user">
        <span className="muted">
          {user.email} · <strong style={{ color: "var(--fg)" }}>{user.role}</strong>
        </span>
        <button className="btn secondary" onClick={onLogout}>
          Log out
        </button>
      </div>
    </nav>
  );
}
