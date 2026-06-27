import type {
  AuthResponse,
  ChatResponse,
  QueryRequest,
  SQLApprovalRequest,
} from "./types";

// Everything is hit through the same-origin /api prefix, which Vite proxies to the
// FastAPI backend (see vite.config.ts). In production, serve the built SPA behind the
// same reverse proxy and this keeps working with no code change.
const API_PREFIX = "/api";

const TOKEN_KEY = "kubepilot_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// Thrown for any non-2xx response. `status` lets callers special-case 401 (re-login)
// and 429 (rate limit / token budget), which the backend uses meaningfully.
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_PREFIX}${path}`, { ...init, headers });

  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`; fall back to status text.
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail[0]?.msg ?? detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export const api = {
  login(username: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  register(username: string, password: string): Promise<AuthResponse> {
    return request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  query(body: QueryRequest): Promise<ChatResponse> {
    return request<ChatResponse>("/query", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  approveSql(body: SQLApprovalRequest): Promise<ChatResponse> {
    return request<ChatResponse>("/query/sql/execute", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};
