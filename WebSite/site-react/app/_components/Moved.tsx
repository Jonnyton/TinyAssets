"use client";

import { useEffect } from "react";
import Link from "next/link";
import styles from "./Moved.module.css";

type MovedProps = {
  /** Destination route, with trailing slash. */
  to: string;
  /** Plain name of the destination page. */
  name: string;
  /** One line saying what the old page became. */
  line: string;
};

/**
 * Soft-landing alias for a retired route. Static export cannot emit a real
 * redirect, so the page says where the content went, links there, and follows
 * after a moment.
 */
export function Moved({ to, name, line }: MovedProps) {
  useEffect(() => {
    const t = setTimeout(() => {
      location.replace(to);
    }, 1800);
    return () => clearTimeout(t);
  }, [to]);

  return (
    <div className={`container narrow ${styles.page}`}>
      <p className="eyebrow">Moved</p>
      <h1 className={styles.title}>{line}</h1>
      <p className={styles.sub}>
        This address is kept so old links still work. You will be taken to {name} in a moment.
      </p>
      <Link className="btn btn--primary btn--md" href={to}>
        Go to {name}
      </Link>
    </div>
  );
}

export default Moved;
