import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";

import { Card, Mono } from "@/components/ui";
import { api } from "@/lib/api";
import type { DiffResult, HistoryRow } from "@/lib/types";
import { verdictColor, VERDICT_LABEL } from "@/lib/verdict";

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

export function Diff() {
  const { email = "" } = useParams();
  const [revs, setRevs] = useState<HistoryRow[]>([]);
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .revisions(email)
      .then((rows) => {
        setRevs(rows);
        if (rows.length >= 2) {
          setA(rows[rows.length - 1].id); // oldest
          setB(rows[0].id); // newest
        }
      })
      .catch((e) => setError(e.message));
  }, [email]);

  useEffect(() => {
    if (a !== null && b !== null && a !== b) {
      api.diff(email, a, b).then(setDiff).catch((e) => setError(e.message));
    } else {
      setDiff(null);
    }
  }, [email, a, b]);

  const changedKeys = useMemo(() => (diff ? Object.keys(diff.changed) : []), [diff]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link to="/history" className="font-mono text-xs underline decoration-dotted" style={{ color: "var(--muted)" }}>
          ← history
        </Link>
        <h1 className="mt-1 text-2xl font-bold tracking-tight">
          <Mono>{email}</Mono>
        </h1>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          {revs.length} stored revision{revs.length === 1 ? "" : "s"} — compare any two.
        </p>
      </div>

      {error && (
        <Card>
          <span style={{ color: "var(--color-undeliverable)" }}>{error}</span>
        </Card>
      )}

      {revs.length >= 2 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["from", a, setA],
              ["to", b, setB],
            ] as const
          ).map(([label, val, set]) => (
            <label key={label} className="flex flex-col gap-1">
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                {label}
              </span>
              <select
                className="rounded-lg border px-3 py-2 font-mono text-sm"
                style={{ background: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
                value={val ?? ""}
                onChange={(e) => set(Number(e.target.value))}
              >
                {revs.map((r) => (
                  <option key={r.id} value={r.id}>
                    #{r.id} · {r.created_at.replace("T", " ").slice(0, 19)} · {r.verdict}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      {diff && (
        <>
          <Card>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                {changedKeys.length} field{changedKeys.length === 1 ? "" : "s"} changed
              </h2>
            </div>
            {changedKeys.length === 0 ? (
              <p style={{ color: "var(--muted)" }}>These revisions differ only in when they were checked.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                      {["field", "from", "to"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {changedKeys.map((k) => (
                      <tr key={k} className="border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                        <td className="px-3 py-2">
                          <Mono>{k}</Mono>
                        </td>
                        <td className="px-3 py-2">
                          <Mono style={{ color: "var(--color-undeliverable)" }}>{fmt(diff.changed[k].from)}</Mono>
                        </td>
                        <td className="px-3 py-2">
                          <Mono style={{ color: "var(--color-deliverable)" }}>{fmt(diff.changed[k].to)}</Mono>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Timeline
            </h2>
            <ol className="flex flex-col gap-2">
              {diff.timeline.map((t) => (
                <li key={t.id} className="flex items-center gap-3 font-mono text-xs">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: verdictColor(t.verdict) }}
                  />
                  <span style={{ color: "var(--muted)" }}>{t.created_at.replace("T", " ").slice(0, 19)}</span>
                  <span style={{ color: verdictColor(t.verdict) }}>
                    {t.verdict ? VERDICT_LABEL[t.verdict] : "—"}
                  </span>
                  <span style={{ color: "var(--muted)" }}>#{t.id}</span>
                </li>
              ))}
            </ol>
          </Card>
        </>
      )}
    </div>
  );
}
