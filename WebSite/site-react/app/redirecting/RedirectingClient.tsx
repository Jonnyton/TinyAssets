"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

export default function RedirectingClient() {
  const router = useRouter();

  React.useEffect(() => {
    let target = "/";
    try {
      const p = new URLSearchParams(window.location.search).get("p");
      // Only honor same-origin absolute paths (never an external URL).
      if (p && p.startsWith("/") && !p.startsWith("//")) target = p;
    } catch {
      /* fall through to home */
    }
    router.replace(target);
  }, [router]);

  return (
    <section className="container" style={{ paddingBlock: "96px" }}>
      <p className="eyebrow">one moment</p>
      <p className="voice">Taking you there…</p>
    </section>
  );
}
