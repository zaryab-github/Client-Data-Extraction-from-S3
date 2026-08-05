// Access-token storage (client-side only). Pure helpers with no imports to avoid
// circular dependencies with the API client.

const TOKEN_KEY = "cde_access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export type CurrentUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  permissions: string[];
  is_active: boolean;
};

export type Shortcode = {
  id: string;
  code: string;
  name: string;
  description: string | null;
};

export type JobReport = {
  csv_row_count: number;
  source_file_count: number;
  source_files?: string[] | null;
  missing_file_count: number;
  rows_scanned: number;
  bad_timestamp_rows: number;
  zip_size_bytes: number;
  checksum_sha256: string | null;
  expires_at: string | null;
};

export type Job = {
  job_id: string;
  status: string;
  requested_shortcodes: string[];
  destination_addrs?: string[] | null;
  date_from: string;
  date_to: string;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  report?: JobReport | null;
};

export type AdminUser = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
};

export type AdminShortcode = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  s3_prefix: string | null;
  s3_file_template: string | null;
  is_active: boolean;
};

export type JobLog = {
  id: number;
  level: string;
  message: string;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  user_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
};
