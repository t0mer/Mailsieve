import type { ButtonHTMLAttributes, CSSProperties, InputHTMLAttributes, ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border p-5 ${className}`}
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed";
  const styles: Record<string, string> = {
    primary: "text-[#0f1418]",
    ghost: "border",
    danger: "text-white",
  };
  const inline =
    variant === "primary"
      ? { background: "var(--color-deliverable)" }
      : variant === "danger"
        ? { background: "var(--color-undeliverable)" }
        : { borderColor: "var(--border)", color: "var(--text)" };
  return (
    <button className={`${base} ${styles[variant]} ${className}`} style={inline} {...rest}>
      {children}
    </button>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-lg border px-3 py-2 font-mono text-sm outline-none ${props.className ?? ""}`}
      style={{ background: "var(--surface-2)", borderColor: "var(--border)", color: "var(--text)" }}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <span
      className="text-xs font-semibold uppercase tracking-wide"
      style={{ color: "var(--muted)" }}
    >
      {children}
    </span>
  );
}

export function Mono({
  children,
  className = "",
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span className={`font-mono ${className}`} style={style}>
      {children}
    </span>
  );
}

export function Spinner() {
  return (
    <span
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      aria-hidden
    />
  );
}
