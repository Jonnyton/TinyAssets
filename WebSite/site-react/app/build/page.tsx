import type { Metadata } from "next";
import BuildClient from "./_components/BuildClient";

export const metadata: Metadata = {
  title: "Build me — two doors into contributing to Tiny",
  description:
    "Two doors into building Tiny: improve the engine through your chatbot without ever cloning code, or clone the Workflow repository and work on it directly. Both end in the same loop — evidence gates, cross-family review, a human merge key.",
  alternates: { canonical: "https://tinyassets.io/build" },
};

export default function BuildPage() {
  return <BuildClient />;
}
