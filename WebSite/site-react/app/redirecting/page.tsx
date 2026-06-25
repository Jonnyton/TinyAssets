// SPA-fallback landing. GitHub Pages (and the preview Worker) serve out/404.html
// for any path that wasn't statically exported — e.g. /goals/<an-id-not-prerendered>/.
// out/404.html bounces here with the original path in `?p=`, and this page
// client-routes to it, so deep-linking any goal works like the old SvelteKit SPA.
// Server page + client child (a top-level "use client" page 404s under output:export).
import type { Metadata } from "next";
import RedirectingClient from "./RedirectingClient";

export const metadata: Metadata = {
  title: "Tiny",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <RedirectingClient />;
}
