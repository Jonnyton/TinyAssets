import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Fine print — Tiny",
  description:
    "The honest economy note — a test rail today, real later — now lives in the Fine print, Tiny's ops room.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function EconomyPage() {
  return (
    <Moved
      to="/fine-print"
      eyebrow="this page moved"
      line={
        <>
          The economy note now lives in the <em>Fine print</em> — kept honest:
          a test rail today, with the real version written as intent, not
          promise.
        </>
      }
      cta="Open the Fine print →"
      sub="/economy → /fine-print · taking you there in a moment"
    />
  );
}
