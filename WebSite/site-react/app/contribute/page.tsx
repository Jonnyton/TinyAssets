import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Build — Tiny",
  description:
    "The contributor path is now Build — clone the engine, run it locally, and the real ways to contribute to Workflow.",
  alternates: { canonical: "https://tinyassets.io/build" },
};

export default function ContributePage() {
  return (
    <Moved
      to="/build"
      eyebrow="this page moved"
      line={
        <>
          Contributing is now <em>Build</em> — clone the open engine, run it
          locally, and every real way to help shape Workflow.
        </>
      }
      cta="Go to Build →"
      sub="/contribute → /build · taking you there in a moment"
    />
  );
}
