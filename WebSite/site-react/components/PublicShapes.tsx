"use client";

import * as React from "react";
import { fetchPublicUniverses } from "../lib/live";
import { fmtRel, fmtStampStable, fmtCount } from "../lib/fmt";
import snapshot from "../lib/mcp-snapshot.json";
import type { Snapshot } from "../lib/types";
import styles from "./PublicShapes.module.css";

type Row = {
  id: string;
  phase: string;
  word_count: number;
  last_activity_at: string | null;
};

type State =
  | { kind: "reading"; rows: Row[]; provenance: string }
  | { kind: "live"; rows: Row[]; fetchedAt: string }
  | { kind: "snapshot"; rows: Row[]; reason: string };

const baked = snapshot as Snapshot;
const bakedRows: Row[] = (baked.universes ?? []).map((u) => ({
  id: u.id,
  phase: u.phase,
  word_count: u.word_count ?? 0,
  last_activity_at: u.last_activity_at ?? null,
}));
const bakedStamp = `checked-in snapshot from ${fmtStampStable(baked.fetched_at)}`;

/**
 * The public universe list, read live through the public read contract
 * (read_graph target=graphs) with the checked-in snapshot as the labelled
 * fallback. A failed live read never relabels the snapshot as live.
 */
export function PublicShapes() {
  const [state, setState] = React.useState<State>({
    kind: "reading",
    rows: bakedRows,
    provenance: bakedStamp,
  });
  const [busy, setBusy] = React.useState(false);

  const refresh = React.useCallback(async () => {
    setBusy(true);
    try {
      const live = await fetchPublicUniverses(100);
      const rows: Row[] = live
        .map((u: any) => ({
          id: String(u.id),
          phase: String(u.phase_human ?? u.phase ?? "unknown"),
          word_count: Number(u.word_count ?? 0),
          last_activity_at: u.last_activity_at ?? null,
        }))
        .sort(
          (a, b) =>
            (Date.parse(b.last_activity_at ?? "") || 0) - (Date.parse(a.last_activity_at ?? "") || 0),
        );
      setState({ kind: "live", rows, fetchedAt: new Date().toISOString() });
    } catch (error) {
      setState({
        kind: "snapshot",
        rows: bakedRows,
        reason: error instanceof Error ? error.message : "Public MCP read is unavailable",
      });
    } finally {
      setBusy(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const rows = state.rows;

  return (
    <div className={styles.wrap} aria-live="polite">
      <div className={styles.bar}>
        {state.kind === "reading" && (
          <span className={styles.stamp}>
            <span className="dot" aria-hidden="true" /> reading the public endpoint… showing the {bakedStamp}
          </span>
        )}
        {state.kind === "live" && (
          <span className={styles.stamp}>
            <span className="dot live" aria-hidden="true" /> live read from tinyassets.io/mcp,{" "}
            {fmtRel(state.fetchedAt)}
          </span>
        )}
        {state.kind === "snapshot" && (
          <span className={styles.stamp}>
            <span className="dot error" aria-hidden="true" /> live read failed ({state.reason}); showing the{" "}
            {bakedStamp}
          </span>
        )}
        <button className="btn btn--ghost btn--sm" onClick={refresh} disabled={busy}>
          {busy ? "reading…" : "Refresh MCP"}
        </button>
      </div>

      {rows.length === 0 ? (
        <p className={styles.empty}>
          No public universes {state.kind === "live" ? "right now" : "in this snapshot"}. Every
          universe starts private; publishing is a choice.
        </p>
      ) : (
        <div className="ledger--wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>Universe</th>
                <th>Phase</th>
                <th>Words</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span className="ev">{r.id}</span>
                  </td>
                  <td>{r.phase}</td>
                  <td>
                    <span className="ev">{fmtCount(r.word_count)}</span>
                  </td>
                  <td>
                    <span className="ev">{r.last_activity_at ? fmtRel(r.last_activity_at) : "—"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="note">
        This page reads only the public projection: universe ids and coarse activity. It never
        downloads operator status or anyone&apos;s contents.
      </p>
    </div>
  );
}

export default PublicShapes;
