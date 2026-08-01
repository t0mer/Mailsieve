import type { ValidationResult } from "@/lib/types";
import { verdictColor, VERDICT_LABEL } from "@/lib/verdict";

type State = "pass" | "fail" | "warn" | "info" | "off" | "unknown";

const STATE_COLOR: Record<State, string> = {
  pass: "var(--color-deliverable)",
  fail: "var(--color-undeliverable)",
  warn: "var(--color-risky)",
  info: "var(--text)",
  off: "var(--cell-off)",
  unknown: "var(--color-unknown)",
};

const STATE_GLYPH: Record<State, string> = {
  pass: "✓",
  fail: "✗",
  warn: "!",
  info: "•",
  off: "–",
  unknown: "?",
};

const boolState = (v: boolean | null): State =>
  v === true ? "pass" : v === false ? "fail" : "unknown";
const riskState = (v: boolean | null): State =>
  v === true ? "warn" : v === false ? "off" : "unknown";
const infoState = (v: boolean | null): State =>
  v === true ? "info" : v === false ? "off" : "unknown";

interface Cell {
  label: string;
  state: State;
}

function Cell({ cell }: { cell: Cell }) {
  const color = STATE_COLOR[cell.state];
  const dim = cell.state === "off" || cell.state === "unknown";
  return (
    <div className="flex min-w-[3.75rem] flex-col items-center gap-1.5">
      <div
        className="flex h-9 w-full items-center justify-center rounded-md text-sm font-bold"
        style={{
          background: dim ? "var(--surface-2)" : color,
          color: dim ? "var(--muted)" : "#0f1418",
          border: `1px solid ${dim ? "var(--border)" : color}`,
        }}
        aria-label={`${cell.label}: ${cell.state}`}
      >
        {STATE_GLYPH[cell.state]}
      </div>
      <span className="font-mono text-[10px] tracking-tight" style={{ color: "var(--muted)" }}>
        {cell.label}
      </span>
    </div>
  );
}

export function SignalStrip({ r }: { r: ValidationResult }) {
  const chain: Cell[] = [
    { label: "format", state: boolState(r.format_valid) },
    { label: "mx", state: boolState(r.mx_found) },
    { label: "smtp", state: boolState(r.smtp_check) },
    { label: "catch-all", state: riskState(r.catch_all) },
  ];
  const tags: Cell[] = [
    { label: "role", state: infoState(r.role) },
    { label: "free", state: infoState(r.free) },
    { label: "disposable", state: riskState(r.disposable) },
  ];

  return (
    <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-start gap-2">
        {chain.map((c) => (
          <Cell key={c.label} cell={c} />
        ))}
        <div className="mx-1 hidden self-stretch border-l sm:block" style={{ borderColor: "var(--border)" }} />
        {tags.map((c) => (
          <Cell key={c.label} cell={c} />
        ))}
      </div>

      <div className="flex items-baseline gap-3 sm:flex-col sm:items-end sm:gap-1">
        <span
          className="text-3xl font-bold leading-none tracking-tight"
          style={{ color: verdictColor(r.verdict) }}
        >
          {VERDICT_LABEL[r.verdict]}
        </span>
        <span className="font-mono text-sm" style={{ color: "var(--muted)" }}>
          score {r.score === null ? "—" : r.score.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
