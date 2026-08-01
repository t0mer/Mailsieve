import type {
  DiffResult,
  HealthResult,
  HistoryPage,
  HistoryRow,
  ValidationResult,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach Mailsieve. Is the service running?");
  }
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* keep default */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  validate: (email: string, force = false) =>
    request<ValidationResult>(`/validate?force=${force}`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  history: (params: {
    limit: number;
    offset: number;
    sort: string;
    order: string;
    search: string;
  }) => {
    const q = new URLSearchParams({
      limit: String(params.limit),
      offset: String(params.offset),
      sort: params.sort,
      order: params.order,
    });
    if (params.search) q.set("search", params.search);
    return request<HistoryPage>(`/history?${q.toString()}`);
  },

  revisions: (email: string) =>
    request<HistoryRow[]>(`/history/${encodeURIComponent(email)}`),

  diff: (email: string, a: number, b: number) =>
    request<DiffResult>(`/history/${encodeURIComponent(email)}/diff?a=${a}&b=${b}`),

  health: () => request<HealthResult>("/health"),

  rotateToken: () => request<{ token: string; warning: string }>("/settings/token", { method: "POST" }),

  settings: () => request<Record<string, unknown>>("/settings"),

  updateTtl: (ttl_days: number) =>
    request<Record<string, unknown>>("/settings", {
      method: "PUT",
      body: JSON.stringify({ ttl_days }),
    }),
};
