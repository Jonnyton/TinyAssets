import * as React from "react";
import "./StatusPill.css";

export type StatusKind = "live" | "idle" | "paid" | "self" | "error";

export interface StatusPillProps {
  /** Pill label (kept short — a daemon state word). */
  children?: React.ReactNode;
  /** Which daemon state. `live` = green heartbeat; `idle` = amber asleep; `paid` = violet; `self` = neutral; `error` = ember. */
  kind?: StatusKind;
  /** Animate the dot (use for genuinely-live states only). */
  pulse?: boolean;
}

/**
 * StatusPill — a daemon-status capsule. The dot colour is load-bearing: green is
 * RESERVED for genuine liveness, amber means asleep (a first-class state, not a
 * failure), ember means error. Set `pulse` only when the state is truly live.
 */
export function StatusPill({ children, kind = "live", pulse = false }: StatusPillProps) {
  return (
    <span className={`pill pill--${kind}`}>
      <span className={`dot${pulse ? " pulse" : ""}`} />
      {children}
    </span>
  );
}

export default StatusPill;
