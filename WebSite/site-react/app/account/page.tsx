import type { Metadata } from "next";
import legal from "../../lib/legal-info.json";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Your account — Tiny",
  description:
    "Your account is your sign-in plus one universe. How to delete it yourself from any TinyAssets app, what is removed immediately, what is kept, and the email fallback.",
  alternates: { canonical: "https://tinyassets.io/account" },
};

export default function AccountPage() {
  return (
    <div className={styles.page}>
      <section className="stub">
        <p className="eyebrow">your account</p>
        <h1>Your account is your sign-in and one universe.</h1>
        <p className="stub__line">
          There is no separate website account. You sign in inside the app — on the
          web at <a href="https://tinyassets.io/mcp/app">tinyassets.io/mcp/app</a>, on
          Android, or on the desktop — and one universe is bound to that sign-in.
          The three apps are the same client, so everything on this page applies to
          all of them.
        </p>

        <h2 id="delete">Delete your account</h2>
        <p className="stub__line">
          You can delete your account yourself, in any of the apps. It takes effect
          immediately and cannot be undone.
        </p>
        <ol className={styles.steps}>
          <li>Open the app (web: tinyassets.io/mcp/app) and sign in.</li>
          <li>Tap <strong>Account</strong> — top right of the chat, or of the Connect screen.</li>
          <li>Type <strong>DELETE</strong> and tap <strong>Delete my account</strong>.</li>
        </ol>
        <p className="stub__line">
          <strong>Removed right away:</strong> your universe — its memory and everything it
          learned, your conversation history, files you sent it, automations you built —
          any AI credential you deposited, connections you added, your grants on other
          universes, your sign-in identity, and any paid plan (cancelled immediately, so
          nothing further is charged).
        </p>
        <p className="stub__line">
          <strong>Kept:</strong> content-free audit records keyed by an opaque id (no name,
          email or content), the invoices our payment processor holds, and server backups
          until they rotate out (at most six months). Nothing that could rebuild your
          universe is retained.
        </p>

        <h2 id="by-email">Can&apos;t sign in? Delete by email</h2>
        <p className="stub__line">
          Email <a href={`mailto:${legal.contact.legal}`}>{legal.contact.legal}</a> from the
          address you signed in with, subject &ldquo;Delete my account&rdquo;. We confirm it is
          you, run the same deletion within 30 days, and reply when it is done. The same
          address handles data-export requests.
        </p>

        <a className="stub__cta" href="https://tinyassets.io/mcp/app">
          Open the app →
        </a>
      </section>
    </div>
  );
}
