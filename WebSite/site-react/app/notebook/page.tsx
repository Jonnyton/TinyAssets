import type { Metadata } from "next";
import { Moved } from "../_components/Moved";

export const metadata: Metadata = {
  title: "Meet Tiny — Tiny",
  description:
    "The notebook is now the front page — meet Tiny, the small living engine, reading from inside himself.",
  alternates: { canonical: "https://tinyassets.io/" },
};

export default function NotebookPage() {
  return (
    <Moved
      to="/"
      eyebrow="this page moved"
      line={
        <>
          The notebook is now the front page — <em>meet Tiny</em>, the small
          living engine, with every page a live reading from inside him.
        </>
      }
      cta="Go to the front page →"
      sub="/notebook → / · taking you there in a moment"
    />
  );
}
