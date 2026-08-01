import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Card, Input, Mono } from "@/components/ui";
import { api } from "@/lib/api";
import type { HistoryPage, Verdict } from "@/lib/types";
import { verdictColor, VERDICT_LABEL } from "@/lib/verdict";

const PAGE_SIZES = [25, 50, 100, 250];
const COLUMNS: { key: string; label: string; sortable: boolean }[] = [
  { key: "email", label: "address", sortable: true },
  { key: "verdict", label: "verdict", sortable: true },
  { key: "score", label: "score", sortable: true },
  { key: "created_at", label: "checked", sortable: true },
  { key: "revisions", label: "revisions", sortable: false },
];

export function History() {
  const [page, setPage] = useState<HistoryPage | null>(null);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    setError(null);
    api
      .history({ limit, offset, sort, order, search: debounced })
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [limit, offset, sort, order, debounced]);

  function toggleSort(key: string) {
    if (sort === key) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setOrder("desc");
    }
    setOffset(0);
  }

  const total = page?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">History</h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            A new row is stored only when a result changes. This is what changed, and when.
          </p>
        </div>
        <div className="w-full sm:w-72">
          <Input
            placeholder="search address…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
            aria-label="Search address"
          />
        </div>
      </div>

      {error && (
        <Card>
          <span style={{ color: "var(--color-undeliverable)" }}>{error}</span>
        </Card>
      )}

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                {COLUMNS.map((c) => (
                  <th key={c.key} className="px-4 py-3 text-left">
                    {c.sortable ? (
                      <button
                        className="font-semibold uppercase tracking-wide"
                        style={{ color: "var(--muted)", fontSize: "11px" }}
                        onClick={() => toggleSort(c.key)}
                      >
                        {c.label}
                        {sort === c.key ? (order === "asc" ? " ↑" : " ↓") : ""}
                      </button>
                    ) : (
                      <span className="font-semibold uppercase tracking-wide" style={{ color: "var(--muted)", fontSize: "11px" }}>
                        {c.label}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {page?.items.map((row) => (
                <tr key={row.id} className="border-b last:border-0" style={{ borderColor: "var(--border)" }}>
                  <td className="px-4 py-2.5">
                    <Mono>{row.email}</Mono>
                  </td>
                  <td className="px-4 py-2.5">
                    <span style={{ color: verdictColor(row.verdict) }} className="font-medium">
                      {row.verdict ? VERDICT_LABEL[row.verdict as Verdict] : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <Mono style={{ color: "var(--muted)" }}>
                      {row.score === null ? "—" : row.score.toFixed(2)}
                    </Mono>
                  </td>
                  <td className="px-4 py-2.5">
                    <Mono className="text-xs" >{row.created_at.replace("T", " ").slice(0, 19)}</Mono>
                  </td>
                  <td className="px-4 py-2.5">
                    {row.revision_count > 1 ? (
                      <Link
                        to={`/diff/${encodeURIComponent(row.email)}`}
                        className="rounded-full px-2 py-0.5 font-mono text-xs"
                        style={{ background: "var(--surface-2)", color: "var(--text)" }}
                      >
                        {row.revision_count} ↗
                      </Link>
                    ) : (
                      <span className="font-mono text-xs" style={{ color: "var(--muted)" }}>1</span>
                    )}
                  </td>
                </tr>
              ))}
              {page && page.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center" style={{ color: "var(--muted)" }}>
                    No results yet. Check an address to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm" style={{ color: "var(--muted)" }}>
        <div className="flex items-center gap-2">
          <span>rows</span>
          <select
            className="rounded-md border px-2 py-1 font-mono"
            style={{ background: "var(--surface)", borderColor: "var(--border)", color: "var(--text)" }}
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value));
              setOffset(0);
            }}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-4">
          <Mono className="text-xs">
            {from}–{to} of {total}
          </Mono>
          <div className="flex gap-2">
            <button
              className="rounded-md border px-3 py-1 disabled:opacity-40"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              prev
            </button>
            <button
              className="rounded-md border px-3 py-1 disabled:opacity-40"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              disabled={to >= total}
              onClick={() => setOffset(offset + limit)}
            >
              next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
