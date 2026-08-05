// API client. Base URL from env (lib/config). Attaches the bearer token on each
// request and clears it on 401 so the UI can redirect to login.

import { config } from "./config";
import {
  clearToken,
  getToken,
  setToken,
  type AdminShortcode,
  type AdminUser,
  type AuditEntry,
  type CurrentUser,
  type Job,
  type JobLog,
  type Shortcode,
} from "./auth";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* ignore parse errors */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// ── Auth actions ─────────────────────────────────────────
type LoginResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: CurrentUser;
};

export async function login(email: string, password: string): Promise<CurrentUser> {
  const res = await apiPost<LoginResponse>("/auth/login", { email, password });
  setToken(res.access_token);
  return res.user;
}

export async function logout(): Promise<void> {
  try {
    await apiPost("/auth/logout", {});
  } catch {
    /* best-effort */
  }
  clearToken();
}

// Renew the access token using the httpOnly refresh cookie (keeps an active
// session alive so only *inactivity* logs the user out).
export async function refreshSession(): Promise<void> {
  const res = await apiPost<LoginResponse>("/auth/refresh");
  setToken(res.access_token);
}

export function getMe(): Promise<CurrentUser> {
  return apiGet<CurrentUser>("/auth/me");
}

export function getShortcodes(): Promise<Shortcode[]> {
  return apiGet<Shortcode[]>("/shortcodes");
}

// ── Jobs ─────────────────────────────────────────────────
export function createJob(
  shortcodes: string[],
  dateFrom: string,
  dateTo: string,
  destinations: string[] = [],
): Promise<Job> {
  return apiPost<Job>("/jobs", {
    shortcodes,
    date_from: dateFrom,
    date_to: dateTo,
    destinations,
  });
}

export function getJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${jobId}`);
}

export function getJobLogs(jobId: string, afterId = 0): Promise<JobLog[]> {
  return apiGet<JobLog[]>(`/jobs/${jobId}/logs?after_id=${afterId}`);
}

export function listJobs(statusFilter?: string): Promise<Job[]> {
  const q = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
  return apiGet<Job[]>(`/jobs${q}`);
}

// Get a short-lived signed link and let the browser stream the ZIP straight to
// disk (native download with progress) — no in-memory buffering of large files.
export async function downloadReport(jobId: string): Promise<void> {
  const { token } = await apiGet<{ token: string }>(`/reports/${jobId}/download-token`);
  const url = `${config.apiBaseUrl}/reports/${jobId}/download?token=${encodeURIComponent(token)}`;
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ── Admin ────────────────────────────────────────────────
export const admin = {
  listUsers: () => apiGet<AdminUser[]>("/admin/users"),
  createUser: (body: { email: string; password: string; full_name?: string; role: string }) =>
    apiPost<AdminUser>("/admin/users", body),
  updateUser: (
    userId: string,
    body: { role?: string; is_active?: boolean; full_name?: string; password?: string },
  ) => request<AdminUser>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteUser: (userId: string) =>
    request<void>(`/admin/users/${userId}`, { method: "DELETE" }),
  listRoles: () => apiGet<{ name: string; permissions: string[] }[]>("/admin/roles"),
  listShortcodes: () => apiGet<AdminShortcode[]>("/admin/shortcodes"),
  createShortcode: (body: { code: string; name: string; description?: string; s3_prefix?: string }) =>
    apiPost<AdminShortcode>("/admin/shortcodes", body),
  listGrants: (userId: string) => apiGet<Shortcode[]>(`/admin/users/${userId}/shortcodes`),
  grant: (userId: string, shortcodes: string[]) =>
    apiPost<{ granted: string[] }>(`/admin/users/${userId}/shortcodes`, { shortcodes }),
  listAudit: () => apiGet<AuditEntry[]>("/admin/audit-logs"),
};

// Phase 1 helper retained for the /health page.
export async function fetchBackendHealth(): Promise<{ status: string } | null> {
  try {
    return await apiGet<{ status: string }>("/health");
  } catch {
    return null;
  }
}
