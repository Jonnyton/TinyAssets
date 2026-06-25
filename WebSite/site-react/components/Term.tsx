import * as React from "react";
import styles from "./Term.module.css";

/** Inline first-use definition — dotted underline, plain-words tip on hover/focus. */
export function Term({ def, children }: { def: string; children?: React.ReactNode }) {
  return (
    <span className={styles.term} tabIndex={0} role="note" aria-label={def}>
      {children}
      <span className={styles.tip} aria-hidden="true">{def}</span>
    </span>
  );
}

export default Term;
