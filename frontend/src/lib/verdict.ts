import type { Verdict } from "./types";

export const VERDICT_COLOR: Record<Verdict, string> = {
  deliverable: "var(--color-deliverable)",
  undeliverable: "var(--color-undeliverable)",
  risky: "var(--color-risky)",
  unknown: "var(--color-unknown)",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  deliverable: "Deliverable",
  undeliverable: "Undeliverable",
  risky: "Risky",
  unknown: "Unknown",
};

export function verdictColor(v: Verdict | null | undefined): string {
  return v ? VERDICT_COLOR[v] : VERDICT_COLOR.unknown;
}
