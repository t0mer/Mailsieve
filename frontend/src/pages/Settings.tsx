import { useEffect, useState } from "react";

import { Button, Card, Input, Label, Mono } from "@/components/ui";
import { api } from "@/lib/api";

interface SettingsView {
  validation: { ttl_days: number };
  auth: { api: { enabled: boolean; token_set: boolean }; ui: { enabled: boolean; username: string } };
  database: { type: string };
  redis: { enabled: boolean };
}

export function Settings() {
  const [view, setView] = useState<SettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ttl, setTtl] = useState("");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");

  function load() {
    api
      .settings()
      .then((v) => {
        const sv = v as unknown as SettingsView;
        setView(sv);
        setTtl(String(sv.validation.ttl_days));
      })
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function saveTtl() {
    try {
      await api.updateTtl(Number(ttl));
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function rotate() {
    try {
      const r = await api.rotateToken();
      setNewToken(r.token);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>

      {error && (
        <Card>
          <span style={{ color: "var(--color-undeliverable)" }}>{error}</span>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 font-semibold">API token</h2>
        <p className="mb-4 text-sm" style={{ color: "var(--muted)" }}>
          {view?.auth.api.token_set ? "A token is set." : "No token set."} Rotating replaces any
          existing token.
        </p>
        {newToken ? (
          <div className="flex flex-col gap-3">
            <div
              className="rounded-lg border-l-4 p-3"
              style={{ background: "var(--surface-2)", borderColor: "var(--color-risky)" }}
            >
              <p className="mb-2 text-sm font-medium" style={{ color: "var(--color-risky)" }}>
                Copy this now — it will not be shown again.
              </p>
              <Mono className="block break-all text-sm">{newToken}</Mono>
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => void navigator.clipboard.writeText(newToken)}>
                Copy
              </Button>
              <Button variant="ghost" onClick={() => setNewToken(null)}>
                I've saved it
              </Button>
            </div>
          </div>
        ) : (
          <Button onClick={() => void rotate()}>
            {view?.auth.api.token_set ? "Rotate token" : "Generate token"}
          </Button>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">Cache lifetime</h2>
        <p className="mb-4 text-sm" style={{ color: "var(--muted)" }}>
          How long a cached result stays fresh, in days. Expiry evicts the cache only — stored
          history is never deleted.
        </p>
        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1">
            <Label>ttl days</Label>
            <Input
              type="number"
              min={1}
              value={ttl}
              onChange={(e) => setTtl(e.target.value)}
              className="w-32"
            />
          </label>
          <Button onClick={() => void saveTtl()}>Save</Button>
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 font-semibold">Backup &amp; restore</h2>
        <p className="mb-4 text-sm" style={{ color: "var(--muted)" }}>
          Download a portable archive, or replace all data from one. Restore is destructive and
          takes a pre-restore snapshot automatically.
        </p>
        <div className="flex flex-col gap-4">
          <form method="post" action="/api/v1/backup">
            <Button type="submit" variant="ghost">
              Download backup
            </Button>
          </form>
          <form
            className="flex flex-col gap-3 border-t pt-4"
            style={{ borderColor: "var(--border)" }}
            method="post"
            action="/api/v1/restore"
            encType="multipart/form-data"
            onSubmit={(e) => {
              if (confirm !== "RESTORE") {
                e.preventDefault();
                setError('Type RESTORE to confirm the destructive restore.');
              }
            }}
          >
            <input type="hidden" name="confirm_token" value={confirm} />
            <label className="flex flex-col gap-1">
              <Label>archive</Label>
              <input
                type="file"
                name="file"
                accept=".gz"
                className="text-sm"
                style={{ color: "var(--text)" }}
              />
            </label>
            <label className="flex flex-col gap-1">
              <Label>type RESTORE to confirm</Label>
              <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="RESTORE" className="w-40" />
            </label>
            <Button type="submit" variant="danger" className="w-40">
              Restore
            </Button>
          </form>
        </div>
      </Card>

      {view && (
        <Card>
          <h2 className="mb-3 font-semibold">Environment</h2>
          <div className="grid gap-x-8 font-mono text-sm sm:grid-cols-2">
            <Row k="database" v={view.database.type} />
            <Row k="redis" v={view.redis.enabled ? "enabled" : "disabled"} />
            <Row k="api auth" v={view.auth.api.enabled ? "on" : "off"} />
            <Row k="ui auth" v={view.auth.ui.enabled ? "on" : "off"} />
          </div>
          <p className="mt-3 text-xs" style={{ color: "var(--muted)" }}>
            Auth modes and bind address are set in config (YAML/env), not here.
          </p>
        </Card>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b py-1.5" style={{ borderColor: "var(--border)" }}>
      <span style={{ color: "var(--muted)" }}>{k}</span>
      <span>{v}</span>
    </div>
  );
}
