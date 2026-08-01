import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import type { HealthResult } from "@/lib/types";

function HealthDot() {
  const [health, setHealth] = useState<HealthResult | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((h) => alive && (setHealth(h), setFailed(false)))
        .catch(() => alive && setFailed(true));
    load();
    const id = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const color = failed
    ? "var(--color-undeliverable)"
    : health?.status === "ok"
      ? "var(--color-deliverable)"
      : "var(--color-risky)";
  const title = failed
    ? "Service unreachable"
    : health
      ? `${health.status} · upstream ${health.provider.reachable ? "reachable" : "unreachable"} · ${health.provider.proxy_count} proxies`
      : "checking…";

  return (
    <span className="flex items-center gap-2 font-mono text-xs" style={{ color: "var(--muted)" }} title={title}>
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
      {health?.version ?? ""}
    </span>
  );
}

export function Layout() {
  const [dark, toggle] = useTheme();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm font-medium transition ${isActive ? "" : "opacity-60 hover:opacity-100"}`;
  const linkStyle = ({ isActive }: { isActive: boolean }) =>
    isActive ? { background: "var(--surface-2)", color: "var(--text)" } : { color: "var(--text)" };

  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col px-4">
      <header
        className="sticky top-0 z-10 -mx-4 mb-8 flex items-center justify-between border-b px-4 py-3 backdrop-blur"
        style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--ground) 82%, transparent)" }}
      >
        <div className="flex items-center gap-6">
          <NavLink to="/" className="flex items-center gap-2">
            <span
              className="inline-block h-4 w-4 rounded-sm"
              style={{ background: "var(--color-deliverable)" }}
            />
            <span className="text-lg font-bold tracking-tight">Mailsieve</span>
          </NavLink>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={linkClass} style={linkStyle}>
              Check
            </NavLink>
            <NavLink to="/history" className={linkClass} style={linkStyle}>
              History
            </NavLink>
            <NavLink to="/settings" className={linkClass} style={linkStyle}>
              Settings
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <HealthDot />
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="rounded-md border px-2 py-1 text-sm"
            style={{ borderColor: "var(--border)", color: "var(--text)" }}
          >
            {dark ? "☾" : "☀"}
          </button>
        </div>
      </header>

      <main className="flex-1 pb-16">
        <Outlet />
      </main>
    </div>
  );
}
