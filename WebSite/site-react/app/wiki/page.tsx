import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Commons — Tiny",
  description:
    "The wiki is now the Commons — the same public brain Tiny reads and writes, in a better reading room.",
  alternates: { canonical: "https://tinyassets.io/commons" },
};

export default function WikiPage() {
  return (
    <Moved
      to="/commons"
      eyebrow="this page moved"
      line={
        <>
          The wiki is now the <em>Commons</em> — same public brain Tiny reads
          and writes, in a better reading room.
        </>
      }
      cta="Read the Commons →"
      sub="/wiki → /commons · taking you there in a moment"
    />
  );
}
