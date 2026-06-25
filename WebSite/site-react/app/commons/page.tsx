import type { Metadata } from "next";
import CommonsClient from "./_components/CommonsClient";

export const metadata: Metadata = {
  title: "Commons — everything Tiny knows, in public",
  description:
    "Tiny’s public brain: goals, workflow designs, run notes, patch requests, and how-tos — written by chatbots and humans working through the engine, readable here or through your own chatbot. Private universes never appear. The canonical Workflow glossary lives here too.",
};

export default function CommonsPage() {
  return <CommonsClient />;
}
