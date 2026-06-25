import type { Metadata } from "next";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "No account needed — Tiny",
  description:
    "There are no website accounts yet — and connecting Tiny needs none. Identity lives in your chatbot connector and your GitHub handle.",
  alternates: { canonical: "https://tinyassets.io/account" },
};

export default function AccountPage() {
  return (
    <div className={styles.page}>
      <section className="stub">
        <p className="eyebrow">no account here</p>
        <h1>Accounts don't exist yet — connecting needs none.</h1>
        <p className="stub__line">
          There's no sign-up to do. Tiny connects through your chatbot's
          connector with one URL, and for code, your GitHub handle is the only
          identity that matters. When website accounts are real — sign-in,
          export, deletion — this page will say so, instead of showing controls
          that do nothing.
        </p>
        <a className="stub__cta" href="/start">
          Connect without an account →
        </a>
      </section>
    </div>
  );
}
