import type { Metadata } from "next";
import CommonsClient from "./_components/CommonsClient";

export const metadata: Metadata = {
  title: "Commons — Tiny's discoverable published knowledge",
  description:
    "A discovery-scoped view of published TinyAssets knowledge, with the server omission note shown beside live counts. It is not a complete inventory.",
};

export default function CommonsPage() {
  return <CommonsClient />;
}
