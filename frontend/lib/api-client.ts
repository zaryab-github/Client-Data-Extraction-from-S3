// API client. Base URL from env (lib/config). Attaches the bearer token on each
// request and clears it on 401 so the UI can redirect to login.

import { config } from "./config";
import { clearToken, getToken, setToken, type CurrentUser, type Shortcode } from "./auth";

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

export function getMe(): Promise<CurrentUser> {
  return apiGet<CurrentUser>("/auth/me");
}

export function getShortcodes(): Promise<Shortcode[]> {
  return apiGet<Shortcode[]>("/shortcodes");
}

// Phase 1 helper retained for the /health page.
export async function fetchBackendHealth(): Promise<{ status: string } | null> {
  try {
    return await apiGet<{ status: string }>("/health");
  } catch {
    return null;
  }
}
