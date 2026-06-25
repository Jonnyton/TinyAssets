import type { Metadata } from "next";
import FinePrintClient from "./_components/FinePrintClient";

export const metadata: Metadata = {
  title: "Vital signs & fine print — Tiny",
  description:
    "The instrument panel: Tiny's live pulse, plain-words explanations of how each reading is measured, the engine's own release receipt, the public watchdogs, and the honest fine print.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function FinePrintPage() {
  return <FinePrintClient />;
}
