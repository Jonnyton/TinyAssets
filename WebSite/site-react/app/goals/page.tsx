import type { Metadata } from "next";
import GoalsClient from "./_components/GoalsClient";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Goals — the board of what Tiny is working on",
  description:
    "The living board of public goals on Tiny. A goal is an outcome; workflows compete to serve it; evidence-gated ladders make the outcome checkable. Read live from the same MCP endpoint your chatbot uses.",
  alternates: { canonical: "https://tinyassets.io/goals" },
};

export default function GoalsPage() {
  return (
    <div className={styles.page}>
      <GoalsClient />
    </div>
  );
}
