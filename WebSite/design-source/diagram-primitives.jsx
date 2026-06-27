// diagram-primitives.jsx
// The visual vocabulary of community-rendered TinyAssets diagrams.
// Cream paper, dusty rose execution bands, sage active nodes, indigo lead, brown checker.
// All extrapolated from real screenshots so re-skins feel like the same artist drew them.

const PALETTE = {
  paper:        "#faf6ee",   // page background
  paperDeep:    "#f1ebdc",   // section bg
  band:         "#d89880",   // dusty rose execution band
  bandStroke:   "#b87560",
  bandLabel:    "#5b3624",
  cream:        "#fbf3e2",   // default node fill
  creamStroke:  "#caa275",
  creamInk:     "#3d2616",
  sage:         "#5e8a5a",   // active dev / writer node
  sageInk:      "#f5f5e8",
  indigo:       "#243a5e",   // lead / coordinator
  indigoInk:    "#f5f5e8",
  amber:        "#a86b2c",   // tester / quality node
  amberInk:     "#fff",
  violetSoft:   "#bcb1d8",   // book-pipeline blue cluster
  violetInk:    "#2a1f4a",
  mint:         "#b9d6bd",   // distribution
  mintInk:      "#1f3a23",
  ember:        "#c44a3a",   // gate diamond
  emberInk:     "#fff",
  green:        "#2f5e35",   // END node (success)
  greenInk:     "#f5f5e8",
  ink:          "#2a1f1a",   // body text
  inkSoft:      "#5b4838",
  hairline:     "rgba(60, 35, 20, 0.18)",
  hairlineSoft: "rgba(60, 35, 20, 0.10)",
  highlight:    "#e94560",   // ember accent — selected/active
  highlightGlow:"rgba(233, 69, 96, 0.35)",
};

window.WF_PALETTE = PALETTE;

// ---------- Atoms ----------

function PaperCard({ children, label, style, accent }) {
  return (
    <figure style={{
      background: PALETTE.paper,
      border: `1px solid ${PALETTE.hairline}`,
      borderRadius: 6,
      padding: "28px 24px 20px",
      margin: 0,
      position: "relative",
      ...style,
    }}>
      {label && (
        <figcaption style={{
          position: "absolute",
          top: 14, left: 22,
          fontFamily: "var(--font-mono)",
          fontSize: 10.5,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: accent || PALETTE.inkSoft,
          fontWeight: 500,
        }}>{label}</figcaption>
      )}
      {children}
    </figure>
  );
}

function Node({ kind = "cream", label, sub, x, y, w = 130, h, selected, onClick, dim, multiline, status }) {
  const k = NODE_STYLES[kind] || NODE_STYLES.cream;
  const heightDefault = sub ? 52 : 36;
  const height = h || heightDefault;
  const isClickable = !!onClick;
  const ringColor = selected ? PALETTE.highlight : k.stroke;
  const ringWidth = selected ? 1.5 : 1;
  return (
    <g transform={`translate(${x}, ${y})`}
       style={{
         cursor: isClickable ? "pointer" : "default",
         opacity: dim ? 0.42 : 1,
         transition: "opacity 240ms cubic-bezier(0.22,1,0.36,1)",
       }}
       onClick={onClick}>
      {selected && (
        <rect x={-4} y={-4} width={w + 8} height={height + 8}
              rx={k.r + 2} fill="none"
              stroke={PALETTE.highlight} strokeWidth={1}
              opacity={0.45}
              style={{ filter: `drop-shadow(0 0 6px ${PALETTE.highlightGlow})` }} />
      )}
      <rect width={w} height={height} rx={k.r}
            fill={k.fill} stroke={ringColor} strokeWidth={ringWidth} />
      {status && (
        <circle cx={10} cy={height/2} r={3.5}
                fill={status === "live" ? "#6dd3a6" : status === "idle" ? "#d9a84a" : "#d89880"} />
      )}
      <text x={w/2} y={sub ? height/2 - 6 : height/2 + 4}
            textAnchor="middle"
            fontFamily="var(--font-sans)"
            fontSize={multiline ? 11.5 : 12.5}
            fontWeight={500}
            fill={k.ink}>
        {Array.isArray(label) ? label.map((l, i) => (
          <tspan key={i} x={w/2} dy={i === 0 ? 0 : 14}>{l}</tspan>
        )) : label}
      </text>
      {sub && (
        <text x={w/2} y={height/2 + 12}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={9.5}
              fontStyle="italic"
              fill={k.ink}
              opacity={0.75}>
          {sub}
        </text>
      )}
    </g>
  );
}

const NODE_STYLES = {
  cream:    { fill: PALETTE.cream,      stroke: PALETTE.creamStroke, ink: PALETTE.creamInk,  r: 4 },
  sage:     { fill: PALETTE.sage,       stroke: "#3f6b3c",           ink: PALETTE.sageInk,   r: 4 },
  indigo:   { fill: PALETTE.indigo,     stroke: "#0e1a32",           ink: PALETTE.indigoInk, r: 4 },
  amber:    { fill: PALETTE.amber,      stroke: "#7a4a18",           ink: PALETTE.amberInk,  r: 4 },
  violet:   { fill: PALETTE.violetSoft, stroke: "#7d6fa8",           ink: PALETTE.violetInk, r: 4 },
  mint:     { fill: PALETTE.mint,       stroke: "#7eaa86",           ink: PALETTE.mintInk,   r: 4 },
  green:    { fill: PALETTE.green,      stroke: "#16331b",           ink: PALETTE.greenInk,  r: 4 },
  ember:    { fill: PALETTE.ember,      stroke: "#7a2818",           ink: PALETTE.emberInk,  r: 4 },
  ghost:    { fill: PALETTE.paperDeep,  stroke: PALETTE.hairline,    ink: PALETTE.inkSoft,   r: 4 },
};

function Diamond({ x, y, label, w = 110, h = 90, selected, onClick, dim, kind = "ember" }) {
  const k = NODE_STYLES[kind] || NODE_STYLES.ember;
  const isClickable = !!onClick;
  return (
    <g transform={`translate(${x}, ${y})`}
       style={{
         cursor: isClickable ? "pointer" : "default",
         opacity: dim ? 0.42 : 1,
         transition: "opacity 240ms cubic-bezier(0.22,1,0.36,1)",
       }}
       onClick={onClick}>
      {selected && (
        <polygon
          points={`${w/2},${-4} ${w + 4},${h/2} ${w/2},${h + 4} ${-4},${h/2}`}
          fill="none" stroke={PALETTE.highlight} strokeWidth={1} opacity={0.5}
          style={{ filter: `drop-shadow(0 0 6px ${PALETTE.highlightGlow})` }} />
      )}
      <polygon
        points={`${w/2},0 ${w},${h/2} ${w/2},${h} 0,${h/2}`}
        fill={k.fill} stroke={selected ? PALETTE.highlight : k.stroke}
        strokeWidth={selected ? 1.5 : 1} />
      <text x={w/2} y={h/2 + 4} textAnchor="middle"
            fontFamily="var(--font-sans)" fontSize={13} fontWeight={600}
            fill={k.ink}>{label}</text>
    </g>
  );
}

// Hand-drawn-feeling band: rounded rect with the dusty rose fill + label tab.
function ExecutionBand({ x, y, w, h, label, accent }) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height={h} rx={8}
            fill={PALETTE.band} fillOpacity={0.55}
            stroke={PALETTE.bandStroke} strokeWidth={1}
            strokeDasharray="0" />
      {label && (
        <text x={w/2} y={14}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={9.5}
              letterSpacing="0.14em"
              fill={accent || PALETTE.bandLabel}
              fontWeight={600}>
          {label.toUpperCase()}
        </text>
      )}
    </g>
  );
}

// Edge: solid by default, dashed when interpreted by outer-runner. Slight curvature.
function Edge({ from, to, dashed, label, labelOffset = 0, color, curve = 0, midpoint, arrow = true, opacity = 1 }) {
  const stroke = color || PALETTE.creamStroke;
  const [x1, y1] = from;
  const [x2, y2] = to;
  let d;
  if (midpoint) {
    const [mx, my] = midpoint;
    d = `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;
  } else if (curve !== 0) {
    const cx = (x1 + x2) / 2 + curve;
    const cy = (y1 + y2) / 2;
    d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
  } else {
    d = `M ${x1} ${y1} L ${x2} ${y2}`;
  }
  return (
    <g opacity={opacity}>
      <path d={d}
            fill="none"
            stroke={stroke}
            strokeWidth={1.25}
            strokeDasharray={dashed ? "5 4" : undefined}
            markerEnd={arrow ? "url(#wf-arrow)" : undefined}
            style={{ transition: "opacity 240ms" }}
      />
      {label && (
        <text x={(x1 + x2) / 2 + labelOffset}
              y={(y1 + y2) / 2 - 4}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={9.5}
              fill={PALETTE.inkSoft}
              opacity={0.85}
              style={{ background: PALETTE.paper }}>
          {label}
        </text>
      )}
    </g>
  );
}

// Annotation: the parchment "post-it" callouts in the screenshots
function Annotation({ x, y, w = 130, lines, accent }) {
  const h = 12 + lines.length * 14;
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect width={w} height={h} rx={3}
            fill="#f6e8d8" stroke={accent || "#d4b48a"} strokeWidth={0.75} />
      {lines.map((l, i) => (
        <text key={i} x={w/2} y={16 + i * 14}
              textAnchor="middle"
              fontFamily="var(--font-sans)"
              fontSize={10.5}
              fill={PALETTE.inkSoft}
              fontStyle={i > 0 ? "italic" : "normal"}>
          {l}
        </text>
      ))}
    </g>
  );
}

// Pen-stroke arrow defs — use once per SVG
function ArrowDefs() {
  return (
    <defs>
      <marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill={PALETTE.creamStroke} />
      </marker>
      <marker id="wf-arrow-soft" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill={PALETTE.inkSoft} opacity={0.6} />
      </marker>
    </defs>
  );
}

// Caption beneath a diagram (the explanatory paragraph)
function DiagCaption({ children, style }) {
  return (
    <p style={{
      fontFamily: "var(--font-sans)",
      fontSize: 14,
      lineHeight: 1.65,
      color: PALETTE.ink,
      margin: "20px 0 0",
      maxWidth: "62ch",
      ...style,
    }}>{children}</p>
  );
}

function InlineCode({ children, kind = "default" }) {
  const styles = {
    default: { bg: "#efe4d0", fg: PALETTE.ink },
    sage:    { bg: PALETTE.sage, fg: PALETTE.sageInk },
    indigo:  { bg: PALETTE.indigo, fg: PALETTE.indigoInk },
    amber:   { bg: PALETTE.amber, fg: "#fff" },
    ember:   { bg: PALETTE.ember, fg: "#fff" },
  };
  const s = styles[kind] || styles.default;
  return (
    <code style={{
      fontFamily: "var(--font-mono)",
      fontSize: "0.88em",
      background: s.bg,
      color: s.fg,
      padding: "1px 5px",
      borderRadius: 3,
      border: "none",
      fontWeight: 500,
    }}>{children}</code>
  );
}

// Small section header (e.g. "1. What happens inside a single node")
function DiagHeader({ num, title, sub }) {
  return (
    <header style={{ marginBottom: 18 }}>
      <h3 style={{
        fontFamily: "var(--font-display)",
        fontSize: 22,
        fontWeight: 500,
        letterSpacing: "-0.01em",
        color: PALETTE.ink,
        margin: "0 0 6px",
      }}>
        <span style={{ color: PALETTE.highlight, fontFamily: "var(--font-mono)", fontSize: 15, marginRight: 10, fontWeight: 500 }}>{num}.</span>
        {title}
      </h3>
      {sub && (
        <p style={{
          fontFamily: "var(--font-sans)",
          fontSize: 14,
          lineHeight: 1.55,
          color: PALETTE.inkSoft,
          margin: 0,
          maxWidth: "70ch",
        }}>{sub}</p>
      )}
    </header>
  );
}

Object.assign(window, {
  PaperCard, Node, Diamond, ExecutionBand, Edge, Annotation, ArrowDefs,
  DiagCaption, InlineCode, DiagHeader, NODE_STYLES,
});
