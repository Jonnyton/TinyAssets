import type { Metadata } from "next";
import GoalDetailClient from "./_components/GoalDetailClient";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Goal — Tiny",
  description:
    "A single goal on Tiny — its outcome, tags, and evidence-gated ladder, read live from the same MCP endpoint your chatbot uses.",
};

// Static export needs a param list to emit pages for a dynamic segment. We
// emit the known goal ids the home page links to; every other id still works
// because the page reads its id from useParams() and pulls the goal live on
// mount (the emitted pages are identical shells — the data is client-fetched).
export function generateStaticParams() {
  return [
    { id: "cbc96a78d7ff" },
    { id: "18b2af05ed32" },
    { id: "d1424d86cb5f" },
  ];
}

export default function GoalDetailPage() {
  return (
    <div className={styles.page}>
      <GoalDetailClient />
    </div>
  );
}
