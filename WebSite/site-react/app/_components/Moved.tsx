"use client";

import { useEffect, type ReactNode } from "react";
import styles from "./Moved.module.css";

type MovedProps = {
  to: string;
  eyebrow: string;
  line: ReactNode;
  cta: string;
  sub: string;
};

export function Moved({ to, eyebrow, line, cta, sub }: MovedProps) {
  useEffect(() => {
    const t = setTimeout(() => {
      location.assign(to);
    }, 2000);

    return () => clearTimeout(t);
  }, [to]);

  return (
    <div className={styles.page}>
      <section className="moved">
        <p className="eyebrow">{eyebrow}</p>
        <p className="moved__line">{line}</p>
        <a className="moved__cta" href={to}>
          {cta}
        </a>
        <p className="moved__sub ev">{sub}</p>
      </section>
    </div>
  );
}
