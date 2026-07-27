import type { Metadata } from "next";
import FinePrintClient from "./_components/FinePrintClient";

export const metadata: Metadata = {
  title: "Vital signs & fine print — Tiny",
  description:
    "The instrument panel: live reachability, visibility-filtered public-universe timestamps, unavailable operator fields, public uptime checks, and honest fine print.",
  alternates: { canonical: "https://tinyassets.io/fine-print" },
};

export default function FinePrintPage() {
  return <FinePrintClient />;
}
