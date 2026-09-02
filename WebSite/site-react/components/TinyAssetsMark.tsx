import * as React from "react";

/**
 * The TinyAssets mark, inline. A ring crossed low by a rule that runs off to
 * the right, with one terracotta dot on the rule. Geometry mirrors
 * `tinyassets/desktop/icon_gen.py` (the single source for every export);
 * colours come from the design tokens so the mark sits on any paper surface.
 */
export function TinyAssetsMark({
  size = 28,
  tile = false,
  title,
}: {
  size?: number;
  /** Draw the rounded paper tile behind the mark (icons, dark grounds). */
  tile?: boolean;
  /** Accessible name; omit for a decorative mark next to a wordmark. */
  title?: string;
}) {
  const id = React.useId().replace(/:/g, "");
  const maskId = `ta-halo-${id}`;
  return (
    <svg
      className="tinyassets-mark"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      style={{ display: "block", flexShrink: 0 }}
    >
      {tile ? (
        <rect width="64" height="64" rx="14" fill="var(--paper-100, #f6f1e6)" />
      ) : (
        <defs>
          <mask id={maskId}>
            <rect width="64" height="64" fill="#fff" />
            <circle cx="32" cy="38" r="8.5" fill="#000" />
          </mask>
        </defs>
      )}
      <circle
        cx="32"
        cy="30"
        r="18.5"
        fill="none"
        stroke="var(--fg-1, #1e1a17)"
        strokeWidth="5"
      />
      <rect
        mask={tile ? undefined : `url(#${maskId})`}
        x="15.5"
        y="36"
        width="43.5"
        height="4"
        fill="var(--fg-1, #1e1a17)"
      />
      {tile && <circle cx="32" cy="38" r="8.5" fill="var(--paper-100, #f6f1e6)" />}
      <circle cx="32" cy="38" r="6" fill="var(--ember-600, #b5471f)" />
    </svg>
  );
}

export default TinyAssetsMark;
