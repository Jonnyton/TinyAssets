"use client";

import { useSearchParams } from "next/navigation";
import GoalDetail from "./_components/GoalDetail";

export default function GoalRoute() {
  const id = useSearchParams().get("id") ?? "";
  return <GoalDetail id={id} />;
}
