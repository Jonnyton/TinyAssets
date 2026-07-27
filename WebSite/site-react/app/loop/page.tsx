import type { Metadata } from "next";
import LoopClient from "./_components/LoopClient";

export const metadata: Metadata = {
  title: "Workflow activity — Tiny",
  description:
    "Public workflow-graph activity from TinyAssets, read through the public graphs collection with explicit provenance.",
};

export default function LoopPage() {
  return <LoopClient />;
}
