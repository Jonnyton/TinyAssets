"use client";

import * as React from "react";
import { fetchVitals, type Vitals } from "../lib/live";
import { fmtRel } from "../lib/fmt";
import { Tick } from "./Tick";
import styles from "./VitalSigns.module.css";

/** Tiny's pulse, read live from the same MCP endpoint visitors paste into a chatbot. */
export function VitalSigns({ variant = "strip" }: { variant?: "hero" | "strip" }) {
  const [vitals, setVitals] = React.useState<Vitals | null>(null);
  const [reading, setReading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    setReading(true);
    const v = await fetchVitals();
    setVitals(v);
    setReading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const cls = `${styles.vitals}${variant === "hero" ? " " + styles.hero : ""}`;

  return (
    <div className={cls} aria-live="polite">
      {reading && !vitals ? (
        <span className={styles.cell}>
          <span className="dot" aria-hidden="true" />
          <span className={styles.k}>reading my vital signs…</span>
        </span>
      ) : vitals && !vitals.reachable ? (
        <>
          <span className={styles.cell}>
            <span className="dot error" aria-hidden="true" />
            <span className={styles.k}>engine unreachable from your browser</span>
          </span>
          <span className={`${styles.cell} ${styles.quiet}`}>
            this is itself a true reading — <span className={styles.ev}>{vitals.error}</span>
          </span>
          <button className={styles.refresh} onClick={refresh} disabled={reading}>
            {reading ? "reading…" : "Refresh MCP"}
          </button>
        </>
      ) : vitals ? (
        <>
          <span className={styles.cell}>
            <span className="dot live" aria-hidden="true" />
            <span className={styles.k}>engine live</span>
            {vitals.deployedAt && (
              <span className={styles.ev}>
                deployed {fmtRel(vitals.deployedAt)}
                {vitals.gitSha ? <>&nbsp;· {vitals.gitSha}</> : null}
              </span>
            )}
          </span>
          <span className={styles.cell}>
            <span className={`dot ${vitals.loopAwake ? "live" : "idle"}`} aria-hidden="true" />
            {vitals.loopAwake && vitals.activeRun ? (
              <span className={styles.k}>loop awake · a run is moving</span>
            ) : vitals.loopAwake ? (
              <>
                <span className={styles.k}>loop awake</span>
                {vitals.lastMovedAt && (
                  <span className={styles.ev}>last signal {fmtRel(vitals.lastMovedAt)}</span>
                )}
              </>
            ) : (
              <>
                <span className={styles.k}>loop asleep</span>
                {vitals.lastMovedAt && (
                  <span className={styles.ev}>last signal {fmtRel(vitals.lastMovedAt)}</span>
                )}
              </>
            )}
          </span>
          {vitals.queue && (
            <span className={styles.cell}>
              <span className={styles.k}>lifetime runs</span>
              <span className={styles.ev}>
                {vitals.queue.succeeded.toLocaleString()} done · {vitals.queue.failed} failed ·{" "}
                {vitals.queue.pending} queued
              </span>
            </span>
          )}
          <span className={`${styles.cell} ${styles.quiet}`}>
            <span className={styles.ev}>read {fmtRel(vitals.fetchedAt)}</span>
            <Tick href="/fine-print" label="how this is measured" />
          </span>
          <button className={styles.refresh} onClick={refresh} disabled={reading}>
            {reading ? "reading…" : "Refresh MCP"}
          </button>
        </>
      ) : null}
    </div>
  );
}

export default VitalSigns;
