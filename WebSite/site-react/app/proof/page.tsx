import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Fine print — Tiny",
  description:
    "The evidence — deploy receipts, run records, and the legal links — now lives in the Fine print, Tiny's ops room.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function ProofPage() {
  return (
    <Moved
      to="/fine-print"
      eyebrow="this page moved"
      line={
        <>
          The evidence now lives in the <em>Fine print</em> — deploy receipts,
          run records, and the legal links, all in Tiny's ops room.
        </>
      }
      cta="Open the Fine print →"
      sub="/proof → /fine-print · taking you there in a moment"
    />
  );
}
