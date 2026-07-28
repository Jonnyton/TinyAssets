import type { Metadata } from "next";
import GraphClient from "./_components/GraphClient";

export const metadata: Metadata = {
  title: "Graph — Tiny's published knowledge map",
  description:
    "A force-directed map of a dated snapshot or a clearly labelled discovery-scoped refresh. Live discovery is not a complete public-page inventory.",
  alternates: {
    canonical: "/graph",
  },
};

export default function GraphPage() {
  return <GraphClient />;
}
