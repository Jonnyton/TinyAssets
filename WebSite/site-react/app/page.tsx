// Home — server component (metadata) rendering the client home. This matches
// the server-page + client-child pattern every other route uses; a top-level
// "use client" page.tsx 404s on hydration under output:export.
import type { Metadata } from "next";
import HomeClient from "./_components/HomeClient";

export const metadata: Metadata = {
  title: "TinyAssets — meet Tiny, the engine that turns chat into finished work",
  description:
    "TinyAssets is the open-source platform behind Tiny, the personified intelligence users meet through MCP. Connect your chatbot to one URL, name a goal, and run real multi-step work with live vital signs and evidence-gated outcome ladders.",
};

export default function Page() {
  return <HomeClient />;
}
