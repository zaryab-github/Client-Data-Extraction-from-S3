// Minimal API client. Base URL comes from config (env-driven). No business logic yet.

import { config } from "./config";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`API GET ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

// Phase 1 helper: check backend liveness from the frontend.
export async function fetchBackendHealth(): Promise<{ status: string } | null> {
  try {
    return await apiGet<{ status: string }>("/health");
  } catch {
    return null;
  }
}
