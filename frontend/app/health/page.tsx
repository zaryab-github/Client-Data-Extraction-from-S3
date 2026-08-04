// Lightweight frontend health page. Pings the backend /health endpoint using the
// env-configured API base URL, confirming end-to-end wiring in later phases.

"use client";

import { useEffect, useState } from "react";
import { fetchBackendHealth } from "@/lib/api-client";
import { config } from "@/lib/config";

export default function HealthPage() {
  const [status, setStatus] = useState<string>("checking...");

  useEffect(() => {
    fetchBackendHealth().then((res) => {
      setStatus(res ? `backend: ${res.status}` : "backend: unreachable");
    });
  }, []);

  return (
    <main>
      <h1>Health</h1>
      <p>Frontend: <code>ok</code></p>
      <p>{status}</p>
      <p className="muted">API base: <code>{config.apiBaseUrl || "(not set)"}</code></p>
    </main>
  );
}
