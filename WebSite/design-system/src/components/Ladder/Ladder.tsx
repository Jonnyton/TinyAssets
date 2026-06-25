import * as React from "react";
import "./Ladder.css";

export type Rung = {
  key?: string;
  name: string;
  description?: string;
  lit?: boolean;
  evidence_url?: string;
};

export interface LadderProps {
  /** Ordered outcome rungs. A rung lights only when `lit` and `evidence_url` are both set. */
  rungs: Rung[];
  /** Short mono label above the ladder. */
  start?: string;
  /** Tightens spacing and hides descriptions. */
  compact?: boolean;
}

/**
 * Ladder — an outcome ladder. Filled rungs require evidence; unlit is the
 * honest default until there is a link proving the outcome.
 */
export function Ladder({ rungs = [], start = "start", compact = false }: LadderProps) {
  return (
    <ol className={`ladder${compact ? " compact" : ""}`}>
      <li className="ladder__start" aria-hidden="true">{start}</li>
      {rungs.map((r, i) => {
        const lit = Boolean(r.lit && r.evidence_url);

        return (
          <li key={r.key ?? r.name ?? i} className={`rung${lit ? " lit" : ""}`}>
            <span className="rung__mark" aria-hidden="true">{lit ? "●" : "○"}</span>
            <span className="rung__body">
              <span className="rung__name">{r.name}</span>
              {!compact && r.description && <span className="rung__desc">{r.description}</span>}
              {lit && r.evidence_url && (
                <a className="rung__evidence" href={r.evidence_url} target="_blank" rel="noreferrer">
                  evidence ↗
                </a>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export default Ladder;
