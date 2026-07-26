import type { Metadata } from "next";
import LoopClient from "./_components/LoopClient";

export const metadata: Metadata = {
  title: "Workflow activity — Tiny",
  description:
    "Recent user-authored workflow activity, read from the TinyAssets MCP connector with explicit live and historical provenance.",
};

export default function LoopPage() {
  return <LoopClient />;
}
