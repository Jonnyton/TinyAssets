import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Workflow patterns — Tiny",
  description:
    "Task automations are ordinary user-authored, remixable workflow designs. Start with a pattern or browse the public commons.",
};

export default function PatchLoopLanding() {
  return (
    <main className={styles.page}>
      <section className={styles.landing} aria-labelledby="landing-title">
        <p className="eyebrow">this product surface retired</p>
        <h1 id="landing-title" className={styles.title}>
          Automations belong to their authors.
        </h1>
        <p className={styles.lede}>
          TinyAssets has no privileged task automation here. People build, publish,
          copy, and remix ordinary workflows from shared primitives. Start with a
          reusable pattern or browse public work in the commons.
        </p>
        <nav className={styles.links} aria-label="Workflow destinations">
          <a className={styles.link} href="/patterns">Explore patterns →</a>
          <a className={styles.link} href="/commons">Browse the commons →</a>
        </nav>
      </section>
    </main>
  );
}
