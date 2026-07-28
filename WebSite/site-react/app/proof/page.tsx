import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Fine print — Tiny",
  description:
    "Public readings, source limits, explicitly unavailable operator fields, and legal links now live in Tiny's Fine print.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function ProofPage() {
  return (
    <Moved
      to="/fine-print"
      eyebrow="this page moved"
      line={
        <>
          Public readings now live in the <em>Fine print</em> — with source
          limits, unavailable operator fields, and legal links labelled plainly.
        </>
      }
      cta="Open the Fine print →"
      sub="/proof → /fine-print · taking you there in a moment"
    />
  );
}
