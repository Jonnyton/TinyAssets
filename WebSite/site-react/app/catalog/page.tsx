import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Goals — Tiny",
  description:
    "The catalog is now the Goals board — the live public list of what Tiny is working toward, each with its outcome ladder.",
  alternates: { canonical: "https://tinyassets.io/goals" },
};

export default function CatalogPage() {
  return (
    <Moved
      to="/goals"
      eyebrow="this page moved"
      line={
        <>
          The catalog is now the <em>Goals board</em> — the live public list of
          what Tiny is working toward, each with its outcome ladder.
        </>
      }
      cta="See the Goals board →"
      sub="/catalog → /goals · taking you there in a moment"
    />
  );
}
