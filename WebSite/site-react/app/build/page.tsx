import type { Metadata } from "next";
import BuildClient from "./_components/BuildClient";

export const metadata: Metadata = {
  title: "Build me — two doors into contributing to Tiny",
  description:
    "Two doors into building Tiny: file public feedback through your chatbot without cloning code, or clone the TinyAssets repository and contribute directly through its documented review process.",
  alternates: { canonical: "https://tinyassets.io/build" },
};

export default function BuildPage() {
  return <BuildClient />;
}
