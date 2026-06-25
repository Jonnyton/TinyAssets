import * as React from "react";
import "./RitualLabel.css";

export interface RitualLabelProps {
  /** Label text — kept short; this is a kicker / eyebrow, not a sentence. */
  children?: React.ReactNode;
  /** Optional colour override (defaults to the muted ink-3). */
  color?: string;
}

/**
 * RitualLabel — the small-caps mono kicker used above section headings and on
 * metadata ("inscribed" text). Mono + wide letter-spacing is the Field Notes
 * signal for a label rather than prose.
 */
export function RitualLabel({ children, color }: RitualLabelProps) {
  return (
    <span className="ritual-label" style={color ? { color } : undefined}>
      {children}
    </span>
  );
}

export default RitualLabel;
