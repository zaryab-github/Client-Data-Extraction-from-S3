"use client";

// Client-side auth guard hook. Fetches the current user; on failure (no/invalid
// token) redirects to /login. The backend independently enforces auth on every call.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe } from "./api-client";
import type { CurrentUser } from "./auth";

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

  return { user, loading };
}
