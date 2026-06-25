import type { Metadata } from "next";
import GraphClient from "./_components/GraphClient";

export const metadata: Metadata = {
  title: "Graph — the living map of Tiny's brain",
  description:
    "A live force-directed map of Tiny's public brain — every wiki page is a dot clustered around its category, goals and universes are their own constellations, and the bright lines are real page-to-page references. Pan, zoom, hover to focus, click through to read.",
  alternates: {
    canonical: "/graph",
  },
};

export default function GraphPage() {
  return <GraphClient />;
}
