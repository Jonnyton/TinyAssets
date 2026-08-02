import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Fine print — Tiny",
  description:
    "Public reachability and timestamp signals, explicitly unavailable operator fields, and legal links now live in Tiny's Fine print.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function StatusPage() {
  return (
    <Moved
      to="/fine-print"
      eyebrow="this page moved"
      line={
        <>
          Public reachability and timestamp signals now live in the{" "}
          <em>Fine print</em>, with unavailable operator fields and legal links
          labelled plainly.
        </>
      }
      cta="Open the Fine print →"
      sub="/status → /fine-print · taking you there in a moment"
    />
  );
}
