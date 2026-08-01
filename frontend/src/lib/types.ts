export type Verdict = "deliverable" | "undeliverable" | "risky" | "unknown";

export interface ValidationResult {
  email: string;
  email_raw: string;
  user: string | null;
  domain: string | null;
  format_valid: boolean | null;
  mx_found: boolean | null;
  smtp_check: boolean | null;
  catch_all: boolean | null;
  role: boolean | null;
  disposable: boolean | null;
  free: boolean | null;
  did_you_mean: string | null;
  score: number | null;
  verdict: Verdict;
  reason: string | null;
  provider: string;
  checked_at: string;
  cached: boolean;
  source: string;
}

export interface HistoryRow {
  id: number;
  email: string;
  verdict: Verdict | null;
  score: number | null;
  created_at: string;
  revision_count: number;
  result: ValidationResult;
}

export interface HistoryPage {
  items: HistoryRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface DiffResult {
  email: string;
  a: HistoryRow;
  b: HistoryRow;
  changed: Record<string, { from: unknown; to: unknown }>;
  timeline: { id: number; created_at: string; verdict: Verdict | null }[];
}

export interface HealthResult {
  status: "ok" | "degraded";
  version: string;
  database: { ok: boolean; type: string };
  redis: { enabled: boolean };
  provider: {
    name: string;
    reachable: boolean;
    secret_ok: boolean;
    proxy_count: number;
    detail: string;
  };
}
