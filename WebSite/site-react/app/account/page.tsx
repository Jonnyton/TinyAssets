import type { Metadata } from "next";
import { RitualLabel } from "@tiny/design-system";
import { SITE } from "../../lib/site";

export const metadata: Metadata = {
  title: "Account",
  description: "Your account lives in the app. How to sign in, and how to delete your account and universe.",
  alternates: { canonical: `${SITE.origin}/account/` },
  robots: { index: false, follow: false },
};

export default function AccountPage() {
  return (
    <section className="container narrow hero">
      <RitualLabel>Account</RitualLabel>
      <h1>Your account lives in the app.</h1>
      <p className="lead">
        Sign in to the web app with your email. Your universe, its brain, its connections and its
        stored files are all bound to that account.
      </p>
      <div className="actions">
        <a className="btn btn--primary btn--lg" href={SITE.app}>
          Open the app
        </a>
      </div>
      <div className="rule" style={{ marginTop: 48 }}>
        <span className="eyebrow">Deleting your account</span>
      </div>
      <p>
        Write to <a href={`mailto:${SITE.contact.legal}`}>{SITE.contact.legal}</a> from the address
        you signed in with. Deletion removes the account, the universe, its brain, every connection
        and credential it holds, and every stored file. There is no in-app control for this yet, so
        this page says so instead of showing one.
      </p>
    </section>
  );
}
