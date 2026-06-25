import type { Metadata } from "next";
import StartClient from "./_components/StartClient";

export const metadata: Metadata = {
  title: "Start — connect your chatbot to Tiny",
  description:
    "Connect your chatbot to Tiny with one URL. Prove the endpoint is live before you paste, follow the Claude.ai or any-MCP-client steps, and bring a starter prompt that works today.",
  alternates: { canonical: "https://tinyassets.io/start" },
};

export default function StartPage() {
  return <StartClient />;
}
