import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Start — Tiny",
  description:
    "Connecting your chatbot now lives at Start — one URL, with a live check that proves the door is open before you paste.",
  alternates: { canonical: "https://tinyassets.io/start" },
};

export default function ConnectPage() {
  return (
    <Moved
      to="/start"
      eyebrow="this page moved"
      line={
        <>
          Connecting your chatbot is now <em>Start</em> — same one-URL paste,
          with a live check that the engine is up before you walk through the
          door.
        </>
      }
      cta="Go to Start →"
      sub="/connect → /start · taking you there in a moment"
    />
  );
}
