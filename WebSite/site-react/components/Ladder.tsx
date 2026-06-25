import * as React from "react";
import styles from "./Ladder.module.css";

export type Rung = {
  key?: string;
  name: string;
  description?: string;
  lit?: boolean;
  evidence_url?: string;
};

/** Gate-ladder visual. A rung lights ONLY with an evidence URL; unlit is honest. */
export function Ladder({
  rungs = [],
  start = "start",
  compact = false,
}: {
  rungs: Rung[];
  start?: string;
  compact?: boolean;
}) {
  return (
    <ol className={`${styles.ladder}${compact ? " " + styles.compact : ""}`}>
      <li className={styles.start} aria-hidden="true">{start}</li>
      {rungs.map((r, i) => (
        <li key={r.key ?? r.name ?? i} className={`${styles.rung}${r.lit ? " " + styles.lit : ""}`}>
          <span className={styles.mark} aria-hidden="true">{r.lit ? "●" : "○"}</span>
          <span className={styles.body}>
            <span className={styles.name}>{r.name}</span>
            {!compact && r.description && <span className={styles.desc}>{r.description}</span>}
            {r.lit && r.evidence_url && (
              <a className={styles.evidence} href={r.evidence_url} target="_blank" rel="noreferrer">
                evidence ↗
              </a>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

export default Ladder;
