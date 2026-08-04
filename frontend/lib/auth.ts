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
