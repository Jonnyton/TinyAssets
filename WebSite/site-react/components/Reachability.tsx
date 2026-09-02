"use client";

import * as React from "react";
import { fetchVitals, type Vitals } from "../lib/live";
import { fmtRel } from "../lib/fmt";
import styles from "./Reachability.module.css";

/**
 * Reachability of the public endpoint from this browser, read through the
 * public projection only (the public universe list). Server reachability and
 * workflow activity are kept as distinct readings, and a failed read is shown
 * as a failed read, never dressed up as anything else.
 */
export function Reachability() {
  const [vitals, setVitals] = React.useState<Vitals | null>(null);
  const [busy, setBusy] = React.useState(true);

  const refresh = React.useCallback(async () => {
    setBusy(true);
    setVitals(await fetchVitals());
    setBusy(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className={styles.strip} aria-live="polite">
      <dl className="receipt" aria-label="Reachability reading">
        {!vitals && (
          <div>
            <dt>endpoint</dt>
            <dd>reading tinyassets.io/mcp from your browser…</dd>
          </div>
        )}
        {vitals && !vitals.reachable && (
          <>
            <div>
              <dt>endpoint</dt>
              <dd className="err">unreachable from your browser</dd>
            </div>
            <div>
              <dt>detail</dt>
              <dd>{vitals.error ?? "Public MCP read is unavailable"}. This is itself a true reading.</dd>
            </div>
          </>
        )}
        {vitals && vitals.reachable && (
          <>
            <div>
              <dt>endpoint</dt>
              <dd className="ok">reachable</dd>
            </div>
            <div>
              <dt>public universes</dt>
              <dd>{vitals.universeCount ?? 0}</dd>
            </div>
            <div>
              <dt>activity</dt>
              <dd>
                {vitals.workflowActive
                  ? `a public universe moved ${vitals.lastMovedAt ? fmtRel(vitals.lastMovedAt) : "recently"}`
                  : vitals.lastMovedAt
                    ? `quiet; last public movement ${fmtRel(vitals.lastMovedAt)}`
                    : "quiet; no public movement recorded"}
              </dd>
            </div>
          </>
        )}
        {vitals && (
          <div>
            <dt>read</dt>
            <dd>{fmtRel(vitals.fetchedAt)}</dd>
          </div>
        )}
      </dl>
      <div className={styles.bar}>
        <button className="btn btn--ghost btn--sm" onClick={refresh} disabled={busy}>
          {busy ? "reading…" : "Refresh MCP"}
        </button>
        <span className="note">
          Reads only the public projection. Reachable does not mean busy: activity is a separate
          reading, and it covers public universes only.
        </span>
      </div>
    </div>
  );
}

export default Reachability;
