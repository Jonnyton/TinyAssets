// Home — server component (metadata) rendering the client home. This matches
// the server-page + client-child pattern every other route uses; a top-level
// "use client" page.tsx 404s on hydration under output:export.
import type { Metadata } from "next";
import HomeClient from "./_components/HomeClient";

export const metadata: Metadata = {
  title: "Tiny — a small living engine that turns chat into finished work",
  description:
    "Tiny is the public face of Workflow, an open-source engine. Connect your chatbot to one URL, name a goal, and it runs real multi-step work — with live vital signs, evidence-gated outcome ladders, and a self-patching loop you can watch.",
};

export default function Page() {
  return <HomeClient />;
}
