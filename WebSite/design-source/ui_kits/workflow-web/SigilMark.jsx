// SigilMark.jsx — the summoning sigil as an <img>, plus a watermark variant.
// The raw SVG lives in assets/logo-mark.svg; we never re-color it.

function SigilMark({ size = 28, style = {} }) {
  return (
    <img
      src="../../assets/logo-mark.svg"
      alt="Workflow"
      width={size}
      height={size}
      style={{ display: "block", ...style }}
    />
  );
}

function SigilWatermark({ size = 520, opacity = 0.06, right = -80, bottom = -80 }) {
  // Used bottom-right of a hero when the space feels empty.
  return (
    <img
      src="../../assets/logo-mark.svg"
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      style={{
        position: "absolute",
        right,
        bottom,
        opacity,
        pointerEvents: "none",
        userSelect: "none",
        filter: "saturate(0.6)",
      }}
    />
  );
}

Object.assign(window, { SigilMark, SigilWatermark });
