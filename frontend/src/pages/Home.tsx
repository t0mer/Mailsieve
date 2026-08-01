import { useState } from "react";

import { SignalStrip } from "@/components/SignalStrip";
import { Button, Card, Input, Label, Mono, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ValidationResult } from "@/lib/types";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-0" style={{ borderColor: "var(--border)" }}>
      <Label>{label}</Label>
      <Mono className="text-sm">{value}</Mono>
    </div>
  );
}

function tri(v: boolean | null): string {
  return v === null ? "—" : v ? "true" : "false";
}

export function Home() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rawOpen, setRawOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function check(force = false) {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await api.validate(email.trim(), force));
    } catch (e) {
      setResult(null);
      setError(
        e instanceof ApiError && e.status === 502
          ? "The upstream verification endpoint is unreachable right now. Try again shortly."
          : e instanceof ApiError
            ? e.message
            : "Something went wrong.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h1 className="mb-1 text-2xl font-bold tracking-tight">Check an address</h1>
        <p className="mb-5 text-sm" style={{ color: "var(--muted)" }}>
          Every address returns a signal fingerprint across the delivery chain and its attributes.
        </p>
        <form
          className="flex flex-col gap-3 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            void check(false);
          }}
        >
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            autoFocus
            aria-label="Email address"
          />
          <Button type="submit" disabled={loading || !email.trim()} className="sm:w-40">
            {loading ? <Spinner /> : "Check address"}
          </Button>
        </form>
      </section>

      {error && (
        <Card className="!border-l-4" >
          <span style={{ color: "var(--color-undeliverable)" }} className="text-sm font-medium">
            {error}
          </span>
        </Card>
      )}

      {result && (
        <>
          <Card>
            <SignalStrip r={result} />
            {result.reason && (
              <p className="mt-4 text-sm" style={{ color: "var(--muted)" }}>
                {result.reason}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-xs" style={{ color: "var(--muted)" }}>
              <span>{result.email}</span>
              <span>·</span>
              <span>{result.cached ? "cached" : `via ${result.source}`}</span>
              {result.did_you_mean && (
                <>
                  <span>·</span>
                  <span>did you mean {result.did_you_mean}?</span>
                </>
              )}
              <button
                className="ml-auto underline decoration-dotted"
                onClick={() => void check(true)}
              >
                re-check (force)
              </button>
            </div>
          </Card>

          <Card>
            <div className="grid gap-x-8 sm:grid-cols-2">
              <Field label="user" value={result.user ?? "—"} />
              <Field label="domain" value={result.domain ?? "—"} />
              <Field label="format valid" value={tri(result.format_valid)} />
              <Field label="mx found" value={tri(result.mx_found)} />
              <Field label="smtp check" value={tri(result.smtp_check)} />
              <Field label="catch all" value={tri(result.catch_all)} />
              <Field label="role" value={tri(result.role)} />
              <Field label="free" value={tri(result.free)} />
              <Field label="disposable" value={tri(result.disposable)} />
              <Field label="checked at" value={result.checked_at} />
            </div>
          </Card>

          <Card>
            <button
              className="flex w-full items-center justify-between text-sm font-medium"
              onClick={() => setRawOpen((o) => !o)}
            >
              <span>Raw response</span>
              <span style={{ color: "var(--muted)" }}>{rawOpen ? "hide" : "show"}</span>
            </button>
            {rawOpen && (
              <div className="mt-3">
                <div className="mb-2 flex justify-end">
                  <button
                    className="font-mono text-xs underline decoration-dotted"
                    style={{ color: "var(--muted)" }}
                    onClick={() => {
                      void navigator.clipboard.writeText(JSON.stringify(result, null, 2));
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }}
                  >
                    {copied ? "copied" : "copy"}
                  </button>
                </div>
                <pre
                  className="overflow-x-auto rounded-lg p-4 font-mono text-xs"
                  style={{ background: "var(--surface-2)" }}
                >
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
