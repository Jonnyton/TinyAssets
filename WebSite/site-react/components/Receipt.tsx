import * as React from "react";

export type ReceiptRow = {
  k: string;
  v: React.ReactNode;
  tone?: "ok" | "err" | "total";
};

/**
 * A run receipt: mono rows between a heavy top rule and a foot rule, the way
 * a real run reports itself. Styles come from the design system's `.receipt`.
 */
export function Receipt({ rows, label }: { rows: ReceiptRow[]; label?: string }) {
  return (
    <dl className="receipt" aria-label={label ?? "Run receipt"}>
      {rows.map((r) => (
        <div key={r.k}>
          <dt>{r.k}</dt>
          <dd className={r.tone ?? undefined}>{r.v}</dd>
        </div>
      ))}
    </dl>
  );
}

export default Receipt;
