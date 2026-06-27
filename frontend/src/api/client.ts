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

// Callbacks the streaming query drives as Server-Sent Events arrive.
export interface StreamHandlers {
  onStage?: (stage: string) => void;
  onToken?: (text: string) => void;
  onDone?: (response: ChatResponse) => void;
  onError?: (err: ApiError) => void;
}

// Map a `done` SSE event (ChatResponse fields at the top level) onto a full ChatResponse,
// filling defaults for anything the streaming path doesn't send.
function toChatResponse(ev: Record<string, unknown>): ChatResponse {
  const meta = (ev.metadata ?? {}) as ChatResponse["metadata"];
  return {
    answer: (ev.answer as string) ?? "",
    sources: (ev.sources as string[]) ?? [],
    confidence: (ev.confidence as number) ?? 0,
    pending_sql: (ev.pending_sql as ChatResponse["pending_sql"]) ?? null,
    cache_hit: (ev.cache_hit as boolean) ?? false,
    cost_saved: (ev.cost_saved as string) ?? "$0.00",
    metadata: meta,
  };
}

// POST /query/stream and dispatch each SSE frame to the handlers. EventSource can't do
// POST + auth headers, so we read the response body stream and parse `data:` frames manually.
export async function queryStream(
  body: QueryRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_PREFIX}/query/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    // Errors raised before streaming starts (400/401/429) come back as a normal JSON body.
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (typeof b?.detail === "string") detail = b.detail;
      else if (Array.isArray(b?.detail)) detail = b.detail[0]?.msg ?? detail;
    } catch {
      // keep statusText
    }
    handlers.onError?.(new ApiError(res.status, detail));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; keep any trailing partial frame in the buffer.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;

      let ev: Record<string, unknown>;
      try {
        ev = JSON.parse(payload);
      } catch {
        continue;
      }

      switch (ev.type) {
        case "stage":
          handlers.onStage?.(ev.stage as string);
          break;
        case "token":
          handlers.onToken?.(ev.text as string);
          break;
        case "done":
          handlers.onDone?.(toChatResponse(ev));
          break;
        case "error":
          handlers.onError?.(new ApiError(500, (ev.detail as string) ?? "stream error"));
          break;
      }
    }
  }
}
