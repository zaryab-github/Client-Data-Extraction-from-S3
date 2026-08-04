// Frontend runtime configuration — sourced entirely from NEXT_PUBLIC_* env vars.
// No URLs, hosts, or IPs are hardcoded.

export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
  maxRangeDays: Number(process.env.NEXT_PUBLIC_MAX_RANGE_DAYS ?? "92"),
  jobPollIntervalMs: Number(process.env.NEXT_PUBLIC_JOB_POLL_INTERVAL_MS ?? "3000"),
  enableAssistant: (process.env.NEXT_PUBLIC_ENABLE_ASSISTANT ?? "false") === "true",
};

export function assertConfigured(): void {
  if (!config.apiBaseUrl) {
    // Surfaced during development so misconfiguration is obvious.
    // eslint-disable-next-line no-console
    console.warn(
      "NEXT_PUBLIC_API_BASE_URL is not set. Copy .env.local.example to .env.local.",
    );
  }
}
