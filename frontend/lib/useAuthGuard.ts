"use client";

// Client-side auth guard hook. Fetches the current user; on failure (no/invalid
// token) redirects to /login. Also enforces an INACTIVITY timeout: while the user is
// active the access token is periodically refreshed; after `idleTimeoutMin` minutes
// with no activity, the session is logged out. The backend independently enforces
// auth on every call.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, logout, refreshSession } from "./api-client";
import { config } from "./config";
import type { CurrentUser } from "./auth";

const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];
const CHECK_INTERVAL_MS = 30_000;
const REFRESH_EVERY_MS = 10 * 60_000; // renew token every 10 min while active

export function useAuthGuard() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getMe()
      .then((u) => {
        if (active) {
          setUser(u);
          setLoading(false);
        }
      })
      .catch(() => router.replace("/login"));
    return () => {
      active = false;
    };
  }, [router]);

  // Inactivity timeout + keep-alive refresh.
  useEffect(() => {
    const idleMs = Math.max(1, config.idleTimeoutMin) * 60_000;
    let lastActivity = Date.now();
    let lastRefresh = Date.now();
    let stopped = false;

    const bump = () => {
      lastActivity = Date.now();
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, bump, { passive: true }));

    const interval = setInterval(async () => {
      const now = Date.now();
      if (now - lastActivity >= idleMs) {
        stopped = true;
        clearInterval(interval);
        await logout();
        router.replace("/login?reason=idle");
        return;
      }
      if (now - lastRefresh >= REFRESH_EVERY_MS) {
        try {
          await refreshSession();
          lastRefresh = now;
        } catch {
          /* a failed refresh will surface as a 401 on the next API call */
        }
      }
    }, CHECK_INTERVAL_MS);

    return () => {
      if (!stopped) clearInterval(interval);
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, bump));
    };
  }, [router]);

  return { user, loading };
}
