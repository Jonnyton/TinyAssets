import * as React from "react";
import "./Term.css";

export interface TermProps {
  /** Plain-words definition shown in the tooltip and exposed as the accessible label. */
  def: string;
  /** The first-use term being defined inline. */
  children?: React.ReactNode;
}

/**
 * Term — inline first-use definition. The dotted underline exposes a plain-words
 * tooltip on hover/focus without interrupting the prose flow.
 */
export function Term({ def, children }: TermProps) {
  return (
    <span className="term" tabIndex={0} role="note" aria-label={def}>
      {children}
      <span className="term__tip" aria-hidden="true">{def}</span>
    </span>
  );
}

export default Term;
