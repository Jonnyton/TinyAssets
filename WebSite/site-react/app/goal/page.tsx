import type { Metadata } from "next";
import { Suspense } from "react";
import GoalRoute from "./GoalRoute";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Goal — Tiny",
  description:
    "A single goal on Tiny — its outcome, tags, and evidence-gated ladder, read live from the same MCP endpoint your chatbot uses.",
};

// Query-param route (`/goal/?id=<id>`): one statically-exported page that renders
// ANY goal client-side. Replaces the dynamic /goals/[id] route, which under
// `output: export` could only emit a fixed set of ids — every other id (and
// even the goals board navigating to a non-prerendered goal) dead-ended on 404.
export default function Page() {
  return (
    <div className={styles.page}>
      <Suspense fallback={null}>
        <GoalRoute />
      </Suspense>
    </div>
  );
}
