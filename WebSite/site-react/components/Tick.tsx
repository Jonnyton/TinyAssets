import * as React from "react";
import styles from "./Tick.module.css";

export interface TickProps {
  href?: string;
  label?: string;
  external?: boolean;
}

/** Provenance device — a small mono tick naming where a value comes from. */
export function Tick({ href = "", label = "source", external = false }: TickProps) {
  if (href) {
    return (
      <a
        className={styles.tick}
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noreferrer" : undefined}
      >
        <span className={styles.glyph} aria-hidden="true">⌁</span>
        {label}
        {external && <span className={styles.ext} aria-hidden="true">↗</span>}
      </a>
    );
  }
  return (
    <span className={`${styles.tick} ${styles.flat}`}>
      <span className={styles.glyph} aria-hidden="true">⌁</span>
      {label}
    </span>
  );
}

export default Tick;
