import type { Metadata } from "next";
import LoopClient from "./_components/LoopClient";

export const metadata: Metadata = {
  title: "The loop — how Tiny patches himself",
  description:
    "Tiny maintains himself through his own product: friction in chat becomes a patch request, runs through investigation and evidence gates, becomes a real GitHub pull request, ships only with a human key, and is watched live. Six stages, the unredacted log, and the live feed — including when the loop is asleep.",
};

export default function LoopPage() {
  return <LoopClient />;
}
