// Phase 1 landing page — a foundation placeholder, no business logic.
// Confirms the frontend starts and reads env-driven config.

import { config } from "@/lib/config";

export default function HomePage() {
  return (
    <main>
      <h1>Client Data Extraction &amp; Delivery System</h1>
      <p className="muted">Frontend foundation is running (Phase 1).</p>

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
        Login, dashboard, extraction, job status, history, and admin screens are
        added in later phases.
      </p>
    </main>
  );
}
