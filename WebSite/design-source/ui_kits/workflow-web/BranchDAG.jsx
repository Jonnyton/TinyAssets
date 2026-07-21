// BranchDAG.jsx — visualizes a branch's node_defs + edges as a phased pipeline.
// This is what makes "branch" concrete. A branch IS a DAG of LLM calls.

const PHASE_COLORS = {
  orient: "var(--violet-400)",
  plan: "var(--violet-500)",
  draft: "var(--ember-500)",
  commit: "var(--ember-600)",
  reflect: "var(--ember-700)",
};

const DEMO_BRANCH_SPEC = {
  name: "deep-space-population-paper",
  parent: "claim-first-iterative",
  author: "@jonnyton",
  goal: "research-paper",
  description: "6-node remix tuned for deep-space-population topics. Absorbs novelty-assessment into scope_framer; replaces generic rigor checks with population-specific audits (Drake params, delta-v, carrying capacity, Fermi reasoning).",
  state_schema: [
    ["seed_angle", "str"],
    ["scope_brief", "str"],
    ["gaps", "list"],
    ["thesis", "str"],
    ["outline", "list"],
    ["draft", "str"],
    ["rigor_notes", "list"],
    ["final_manuscript", "str"],
  ],
  nodes: [
    { id: "scope_framer", phase: "orient", input: ["seed_angle"], output: ["scope_brief"] },
    { id: "gap_finder", phase: "orient", input: ["scope_brief"], output: ["gaps"] },
    { id: "thesis_architect", phase: "plan", input: ["scope_brief", "gaps"], output: ["thesis", "outline"] },
    { id: "section_drafter", phase: "draft", input: ["thesis", "outline"], output: ["draft"] },
    { id: "rigor_checker", phase: "commit", input: ["draft"], output: ["rigor_notes"] },
    { id: "revision_orchestrator", phase: "reflect", input: ["draft", "rigor_notes"], output: ["final_manuscript"] },
  ],
};

function NodeTile({ node, running = false }) {
  const color = PHASE_COLORS[node.phase] || "var(--fg-3)";
  return (
    <div style={{ background: "var(--bg-2)", border: `1px solid ${running ? color : "var(--border-1)"}`, borderRadius: 10, padding: "14px 16px", minWidth: 180, boxShadow: running ? `0 0 0 1px ${color}, 0 0 20px ${color}30` : "none", transition: "all 220ms var(--ease-summon)" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.14em", color, marginBottom: 6 }}>
        ◇ {node.phase}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--fg-1)", marginBottom: 10 }}>
        {node.id}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", lineHeight: 1.5 }}>
        <div>in: {node.input.join(", ")}</div>
        <div>→ out: <span style={{ color: "var(--ember-500)" }}>{node.output.join(", ")}</span></div>
      </div>
    </div>
  );
}

function BranchDAG({ spec = DEMO_BRANCH_SPEC, runningNodeIdx = -1 }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {spec.nodes.map((n, i) => (
          <React.Fragment key={n.id}>
            <NodeTile node={n} running={i === runningNodeIdx} />
            {i < spec.nodes.length - 1 && (
              <div style={{ fontFamily: "var(--font-mono)", color: "var(--fg-4)", fontSize: 18 }}>→</div>
            )}
          </React.Fragment>
        ))}
      </div>
      <div style={{ marginTop: 20, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {["orient", "plan", "draft", "commit", "reflect"].map((p) => (
          <div key={p} style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: PHASE_COLORS[p] }} />
            {p}
          </div>
        ))}
      </div>
    </div>
  );
}

function StateSchemaTable({ schema }) {
  return (
    <div style={{ background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "14px 18px", fontFamily: "var(--font-mono)", fontSize: 11, lineHeight: 1.9 }}>
      {schema.map(([name, type], i) => (
        <div key={i} style={{ display: "flex", gap: 12 }}>
          <span style={{ color: "var(--fg-3)", width: 20, textAlign: "right" }}>{String(i).padStart(2, "0")}</span>
          <span style={{ color: "var(--ember-600)", minWidth: 180 }}>{name}</span>
          <span style={{ color: "var(--violet-400)" }}>{type}</span>
        </div>
      ))}
    </div>
  );
}

Object.assign(window, { DEMO_BRANCH_SPEC, BranchDAG, StateSchemaTable, NodeTile, PHASE_COLORS });
