import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Fine print — Tiny",
  description:
    "Live status, deploy receipts, and the legal links now live in the Fine print — Tiny's ops room.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function StatusPage() {
  return (
    <Moved
      to="/fine-print"
      eyebrow="this page moved"
      line={
        <>
          Live status now lives in the <em>Fine print</em> — Tiny's ops room,
          with deploy receipts and the legal links alongside it.
        </>
      }
      cta="Open the Fine print →"
      sub="/status → /fine-print · taking you there in a moment"
    />
  );
}
