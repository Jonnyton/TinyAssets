import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Start — Tiny",
  description:
    "The patterns page is now Start — connect your chatbot with one URL and bring a first prompt that works today.",
  alternates: { canonical: "https://tinyassets.io/start" },
};

export default function PatternsPage() {
  return (
    <Moved
      to="/start"
      eyebrow="this page moved"
      line={
        <>
          The patterns page is now <em>Start</em> — connect your chatbot with
          one URL, then bring a first prompt for whichever kind of work you do.
        </>
      }
      cta="Go to Start →"
      sub="/patterns → /start · taking you there in a moment"
    />
  );
}
