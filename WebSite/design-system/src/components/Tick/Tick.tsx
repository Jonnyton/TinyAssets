import * as React from "react";
import "./Tick.css";

export interface TickProps {
  /** Link target for the provenance source. When omitted, renders a flat inline tick. */
  href?: string;
  /** Short source label. */
  label?: string;
  /** Opens the link in a new tab and shows the external marker. */
  external?: boolean;
}

/**
 * Tick — a provenance device. The mono glyph and label name where a value or
 * claim comes from; render as an anchor when `href` is provided.
 */
export function Tick({ href = "", label = "source", external = false }: TickProps) {
  if (href) {
    return (
      <a
        className="tick"
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noreferrer" : undefined}
      >
        <span className="tick__glyph" aria-hidden="true">⌁</span>
        {label}
        {external && <span className="tick__ext" aria-hidden="true">↗</span>}
      </a>
    );
  }

  return (
    <span className="tick tick--flat">
      <span className="tick__glyph" aria-hidden="true">⌁</span>
      {label}
    </span>
  );
}

export default Tick;
