// Landing page. Links to sign-in; the dashboard is protected.

import Link from "next/link";
import { config } from "@/lib/config";

export default function HomePage() {
  return (
    <main>
      <h1>Client Data Extraction &amp; Delivery System</h1>
      <p className="muted">Phase 2: authentication &amp; authorization.</p>

      <p style={{ marginTop: 24 }}>
        <Link href="/login">Sign in →</Link>
      </p>

      <h2>Configuration</h2>
      <ul>
        <li>
          API base URL:{" "}
          <code>{config.apiBaseUrl || "(not set — see .env.local.example)"}</code>
        </li>
        <li>Max range days: <code>{config.maxRangeDays}</code></li>
        <li>Job poll interval (ms): <code>{config.jobPollIntervalMs}</code></li>
        <li>AI assistant enabled: <code>{String(config.enableAssistant)}</code></li>
      </ul>

      <p className="muted">
        Extraction, job status, history, and admin screens are added in later phases.
      </p>
    </main>
  );
}
