// Diagrams.jsx — rewritten to match the reference clarity:
// clean boxed flowcharts, two-tone (violet = prep/generative, green = review/refinement),
// vertical for process flows, horizontal for high-level ribbons, dashed group containers.

// Shared tokens for this family of diagrams
const D = {
  neutral: { fill: "var(--bg-3)", stroke: "var(--border-2)", text: "var(--fg-1)", meta: "var(--fg-3)" },
  prep:    { fill: "rgba(83, 52, 131, 0.22)", stroke: "rgba(138, 99, 206, 0.55)", text: "var(--fg-1)", meta: "var(--violet-200)" },
  review:  { fill: "rgba(109, 211, 166, 0.14)", stroke: "rgba(109, 211, 166, 0.55)", text: "var(--fg-1)", meta: "var(--signal-live)" },
  accent:  { fill: "rgba(233, 69, 96, 0.14)", stroke: "var(--ember-600)", text: "var(--fg-1)", meta: "var(--ember-500)" },
  dashed:  "1px dashed rgba(255,255,255,0.18)",
};

// Generic flowchart node
function FlowNode({ title, sub, tone = "neutral", width = 220, code = false }) {
  const t = D[tone];
  return (
    <div style={{
      background: t.fill,
      border: `1px solid ${t.stroke}`,
      borderRadius: 8,
      padding: "12px 16px",
      width,
      textAlign: "center",
    }}>
      <div style={{
        fontFamily: code ? "var(--font-mono)" : "var(--font-sans)",
        fontSize: 13,
        fontWeight: 600,
        color: t.text,
        marginBottom: sub ? 4 : 0,
      }}>{title}</div>
      {sub && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: t.meta, lineHeight: 1.4 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

// Arrow with optional label (direction: down | right)
function Arrow({ direction = "down", label, labelSide = "right", length = 28 }) {
  if (direction === "right") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "0 6px", minWidth: 24 }}>
        <div style={{ width: length, height: 1, background: "var(--fg-3)", position: "relative" }}>
          <span style={{ position: "absolute", right: -1, top: -4, width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: "6px solid var(--fg-3)" }} />
        </div>
        {label && <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", marginTop: 4 }}>{label}</div>}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "4px 0", gap: 10, position: "relative" }}>
      <div style={{ width: 1, height: length, background: "var(--fg-3)", position: "relative", marginLeft: labelSide === "right" ? 110 : 0 }}>
        <span style={{ position: "absolute", left: -4, bottom: -1, width: 0, height: 0, borderLeft: "4px solid transparent", borderRight: "4px solid transparent", borderTop: "6px solid var(--fg-3)" }} />
      </div>
      {label && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)" }}>
          {label}
        </div>
      )}
    </div>
  );
}

// Dashed group container
function FlowGroup({ title, children, style }) {
  return (
    <div style={{
      border: D.dashed,
      borderRadius: 12,
      padding: "22px 18px 18px",
      position: "relative",
      ...style,
    }}>
      <div style={{
        position: "absolute", top: -9, left: 16, background: "var(--bg-2)", padding: "0 10px",
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em",
      }}>{title}</div>
      {children}
    </div>
  );
}

// Legend
function Legend({ items }) {
  return (
    <div style={{ display: "flex", gap: 20, marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border-1)", flexWrap: "wrap" }}>
      {items.map(([color, label]) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: D[color].fill, border: `1px solid ${D[color].stroke}` }} />
          {label}
        </div>
      ))}
    </div>
  );
}

const vstack = { display: "flex", flexDirection: "column", alignItems: "center" };
const hstack = { display: "flex", alignItems: "center" };

// ----------------------------------------------------------------
// 1 · LIFECYCLE — horizontal ribbon with loopback arrow
// ----------------------------------------------------------------
function DiagramLifecycle() {
  const phases = [
    { title: "Plan", sub: "outline + bible", tone: "neutral" },
    { title: "Draft", sub: "scene loop", tone: "prep" },
    { title: "Integrate", sub: "assemble + canon check", tone: "prep" },
    { title: "Produce", sub: "copy edit, format", tone: "review" },
    { title: "Publish", sub: "distribute + verify", tone: "review" },
  ];
  return (
    <div style={diagramFrame}>
      <div style={{ ...hstack, justifyContent: "center", gap: 2 }}>
        {phases.map((p, i) => (
          <React.Fragment key={p.title}>
            <FlowNode {...p} width={160} />
            {i < phases.length - 1 && <Arrow direction="right" length={22} />}
          </React.Fragment>
        ))}
      </div>
      <div style={{ marginTop: 16, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", fontStyle: "italic" }}>
        ↺ reader signal and reviews feed back into Plan for book N+1
      </div>
      <Legend items={[["neutral", "input / output"], ["prep", "preparation + creation"], ["review", "review + production"]]} />
    </div>
  );
}

// ----------------------------------------------------------------
// 2 · CREW — two-row crew with connector from row1-end down & over to row2-start
// ----------------------------------------------------------------
function DiagramCrew() {
  const NODE_W = 170;
  const GAP = 22;            // arrow/gap width between nodes
  const ROW_H = 56;
  const TOTAL_W = NODE_W * 3 + GAP * 2;

  // connector: down from under Scribe (last of row1), horizontal all the way left to above Continuity (first of row2), down into it
  // Scribe center-x = NODE_W + GAP + NODE_W + GAP + NODE_W/2
  const scribeCenterX = NODE_W * 2 + GAP * 2 + NODE_W / 2;
  const contCenterX = NODE_W / 2;

  const prep = [
    { title: "Lorekeeper", sub: "canon retrieval" },
    { title: "Architect", sub: "scene structure" },
    { title: "Scribe", sub: "prose generation" },
  ];
  const review = [
    { title: "Continuity editor", sub: "canon consistency" },
    { title: "Prose polisher", sub: "line editing" },
    { title: "Beta reader", sub: "reader experience" },
  ];

  return (
    <div style={diagramFrame}>
      <div style={{ width: TOTAL_W, margin: "0 auto", position: "relative" }}>
        {/* Row 1 */}
        <div style={{ ...hstack, gap: 0 }}>
          {prep.map((p, i) => (
            <React.Fragment key={p.title}>
              <FlowNode {...p} tone="prep" width={NODE_W} />
              {i < prep.length - 1 && <Arrow direction="right" length={GAP - 4} />}
            </React.Fragment>
          ))}
        </div>

        {/* Connector from Scribe-bottom down, left across, and down into Continuity-top */}
        <div style={{ position: "relative", height: 40 }}>
          {/* down segment from Scribe */}
          <div style={{ position: "absolute", left: scribeCenterX - 0.5, top: 0, width: 1, height: 20, background: "var(--fg-3)" }} />
          {/* horizontal segment */}
          <div style={{ position: "absolute", left: contCenterX, top: 19, width: scribeCenterX - contCenterX, height: 1, background: "var(--fg-3)" }} />
          {/* down into Continuity with arrowhead */}
          <div style={{ position: "absolute", left: contCenterX - 0.5, top: 20, width: 1, height: 20, background: "var(--fg-3)" }} />
          <div style={{
            position: "absolute", left: contCenterX - 4, top: 35,
            width: 0, height: 0,
            borderLeft: "4px solid transparent", borderRight: "4px solid transparent",
            borderTop: "6px solid var(--fg-3)",
          }} />
        </div>

        {/* Row 2 */}
        <div style={{ ...hstack, gap: 0 }}>
          {review.map((p, i) => (
            <React.Fragment key={p.title}>
              <FlowNode {...p} tone="review" width={NODE_W} />
              {i < review.length - 1 && <Arrow direction="right" length={GAP - 4} />}
            </React.Fragment>
          ))}
        </div>
      </div>
      <Legend items={[["prep", "preparation + creation"], ["review", "review + refinement"]]} />
    </div>
  );
}

// ----------------------------------------------------------------
// 3 · CRITIQUE GATE — vertical flow with fail loopback (DOM-based lines)
// ----------------------------------------------------------------
function DiagramCritique() {
  // Layout is fixed-width so we can place the loopback arc precisely.
  // Column is 280px wide, centered. Loopback lives in a 120px gutter on the left.
  const W = 280;
  const GUTTER = 120;
  return (
    <div style={diagramFrame}>
      <div style={{ position: "relative", width: W + GUTTER, margin: "0 auto" }}>
        {/* Loopback: from Critique-gate left (y≈212) up to Scribe left (y≈120),
            arrowhead pointing INTO Scribe's left edge. Using DOM-box lines. */}
        {/* horizontal stub out of Critique gate */}
        <div style={{
          position: "absolute", left: 40, top: 212, width: GUTTER - 40, height: 1,
          borderTop: "1px dashed var(--ember-600)",
        }} />
        {/* vertical run upward */}
        <div style={{
          position: "absolute", left: 40, top: 120, width: 1, height: 92,
          borderLeft: "1px dashed var(--ember-600)",
        }} />
        {/* horizontal stub into Scribe */}
        <div style={{
          position: "absolute", left: 40, top: 120, width: GUTTER - 32, height: 1,
          borderTop: "1px dashed var(--ember-600)",
        }} />
        {/* arrowhead pointing right, INTO Scribe's left edge */}
        <div style={{
          position: "absolute", left: GUTTER + 2, top: 116,
          width: 0, height: 0,
          borderTop: "5px solid transparent", borderBottom: "5px solid transparent",
          borderLeft: "7px solid var(--ember-600)",
        }} />
        {/* fail label, sitting in the middle of the vertical run */}
        <div style={{
          position: "absolute", left: 50, top: 152,
          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ember-600)",
          lineHeight: 1.3, width: 70,
        }}>
          fail<br/>+ critique
        </div>

        {/* the flow column */}
        <div style={{ marginLeft: GUTTER, ...vstack, alignItems: "flex-start" }}>
          <FlowNode title="Assemble prompt" sub="canon context · scene plan · prior state" tone="neutral" width={W} />
          <Arrow direction="down" labelSide="none" />
          <FlowNode title="Scribe drafts scene" sub="initial prose" tone="prep" width={W} />
          <Arrow direction="down" labelSide="none" />
          <FlowNode title="Critique gate" sub="voice · canon · pacing · character · prose" tone="prep" width={W} />
          <Arrow direction="down" labelSide="right" label="pass" />
          <FlowNode title="Continuity check" sub="canon cross-reference across books" tone="prep" width={W} />
          <Arrow direction="down" labelSide="none" />
          <FlowNode title="Commit to chapter worktree" sub="update status.md and plan.md" tone="neutral" width={W} />
        </div>
      </div>
      <div style={{ marginTop: 16, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        N ≤ 3 revision cycles · then human escalation
      </div>
      <Legend items={[["neutral", "I/O"], ["prep", "scribe loop"], ["accent", "fail-path feedback"]]} />
    </div>
  );
}

// ----------------------------------------------------------------
// 4 · CANON — vertical tree, router fans to 3, merges at synthesizer
// ----------------------------------------------------------------
function DiagramCanon() {
  return (
    <div style={diagramFrame}>
      <div style={vstack}>
        <FlowNode title="Canon query" sub="from Scribe or Architect" tone="neutral" width={260} />
        <Arrow direction="down" labelSide="none" />
        <FlowNode title="Agentic router" sub="classifies query intent" tone="prep" width={260} />
      </div>

      {/* Three-way fan */}
      <div style={{ position: "relative", height: 34, margin: "0 auto", maxWidth: 640 }}>
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <defs>
            <marker id="arr-fan" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--fg-3)"/>
            </marker>
          </defs>
          <line x1="50%" y1="0" x2="16%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
          <line x1="50%" y1="0" x2="50%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
          <line x1="50%" y1="0" x2="84%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
        </svg>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, maxWidth: 720, margin: "0 auto" }}>
        <FlowNode title="GraphRAG" sub={<>factions, relationships<br/>multi-hop entity queries</>} tone="review" width="100%" />
        <FlowNode title="Vector search" sub={<>vibe, similar scenes<br/>thematic matches</>} tone="review" width="100%" />
        <FlowNode title="Direct lookup" sub={<>named passages<br/>chapter references</>} tone="review" width="100%" />
      </div>

      {/* Merge back */}
      <div style={{ position: "relative", height: 34, margin: "0 auto", maxWidth: 640 }}>
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          <line x1="16%" y1="0" x2="50%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
          <line x1="50%" y1="0" x2="50%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
          <line x1="84%" y1="0" x2="50%" y2="100%" stroke="var(--fg-3)" strokeWidth="1" markerEnd="url(#arr-fan)" />
        </svg>
      </div>

      <div style={vstack}>
        <FlowNode title="Synthesizer" sub="merge, rerank, cite sources" tone="prep" width={260} />
        <Arrow direction="down" labelSide="none" />
        <FlowNode title="Canon context" sub="prompt-ready with citations" tone="neutral" width={260} />
      </div>

      <Legend items={[["neutral", "query / output"], ["prep", "routing + synthesis"], ["review", "retrieval backends"]]} />
    </div>
  );
}

// ----------------------------------------------------------------
// 5 · HANDOFF — Manuscript → Production group → distribution channels
// ----------------------------------------------------------------
function DiagramHandoff() {
  return (
    <div style={diagramFrame}>
      <div style={{ ...hstack, gap: 16, alignItems: "stretch", justifyContent: "center" }}>
        {/* Manuscript */}
        <div style={{ ...vstack, justifyContent: "center" }}>
          <FlowNode title="Manuscript" sub="all chapters assembled" tone="neutral" width={170} />
        </div>
        <div style={{ ...vstack, justifyContent: "center" }}>
          <Arrow direction="right" length={28} />
        </div>

        {/* Production group */}
        <FlowGroup title="Production" style={{ padding: "24px 22px 18px" }}>
          <div style={{ ...vstack, gap: 0 }}>
            <FlowNode title="Copy edit" tone="prep" width={220} />
            <Arrow direction="down" labelSide="none" length={22} />
            <FlowNode title="Format: epub + PDF" tone="prep" width={220} />
            <Arrow direction="down" labelSide="none" length={22} />
            <FlowNode title="Cover + metadata" tone="prep" width={220} />
          </div>
        </FlowGroup>

        {/* Fan to channels */}
        <div style={{ ...vstack, justifyContent: "space-around", padding: "8px 0" }}>
          {[0,1,2,3].map(i => (
            <div key={i} style={{ width: 28, height: 1, background: "var(--fg-3)", position: "relative", margin: "8px 0" }}>
              <span style={{ position: "absolute", right: -1, top: -4, width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: "6px solid var(--fg-3)" }} />
            </div>
          ))}
        </div>

        {/* Channels */}
        <div style={{ ...vstack, gap: 10 }}>
          <FlowNode title="KDP" sub="print + ebook" tone="review" width={170} />
          <FlowNode title="Apple Books" sub="ebook" tone="review" width={170} />
          <FlowNode title="Kobo" sub="ebook, intl." tone="review" width={170} />
          <FlowNode title="IngramSpark" sub="print retail" tone="review" width={170} />
        </div>
      </div>
      <Legend items={[["neutral", "manuscript"], ["prep", "production"], ["review", "distribution"]]} />
    </div>
  );
}

const diagramFrame = {
  background: "var(--bg-2)",
  border: "1px solid var(--border-1)",
  borderRadius: 14,
  padding: "32px 28px 24px",
};

Object.assign(window, { DiagramLifecycle, DiagramCrew, DiagramCritique, DiagramCanon, DiagramHandoff });
