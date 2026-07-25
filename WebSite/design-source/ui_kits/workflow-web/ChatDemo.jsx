// ChatDemo.jsx — a faux transcript showing the actual interaction pattern.
// This is the single most important "show, don't tell" moment on the site.

const TRANSCRIPT = [
  { role: "user", text: "hey, I want to use workflow — trying to design a pipeline for writing a research paper on deep-space population. can you help me build it?" },
  { role: "thought", text: "Mapping jonnyton's existing pipeline architectures and configurations" },
  { role: "tool", text: "workflow.list_branches(goal=\"research-paper\")" },
  { role: "assistant", text: "Happy to help. You've got three branches in play on research-paper already: claim-first-iterative (7 nodes), replication-focused (9 nodes), and adversarial-peer (5 nodes). A 6-node remix feels right — I'll fold novelty-assessment into scope_framer and drop the standalone insight_tracker." },
  { role: "thought", text: "Reconciled timeline context and prepared to load workflow tools" },
  { role: "assistant", text: "Here's the paste-ready spec. Six nodes, split 3-and-3 between upstream planning (orient/plan) and downstream writing (draft/commit/reflect). Rigor checker is the node that earns the remix — it audits the six population-specific failure modes deep-space papers stumble on: Drake hand-waving, delta-v math, closed-biosphere budgets, cosmological consistency, OoM slips, Fermi robustness.", spec: true },
  { role: "assistant", text: "Goal-bound to research-paper. Same leaderboard as the other three when Phase 6 outcome ranking lands. Want me to build_branch as soon as the daemon's back?" },
];

function ChatMessage({ m }) {
  if (m.role === "user") {
    return (
      <div style={{ alignSelf: "flex-end", maxWidth: "78%", background: "var(--bg-3)", border: "1px solid var(--border-1)", borderRadius: "14px 14px 4px 14px", padding: "12px 16px", fontSize: 13.5, color: "var(--fg-1)", lineHeight: 1.55 }}>
        {m.text}
      </div>
    );
  }
  if (m.role === "thought") {
    return (
      <div style={{ alignSelf: "flex-start", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", fontStyle: "italic", padding: "6px 2px", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 3, height: 3, borderRadius: "50%", background: "var(--violet-400)" }} />
        {m.text}
      </div>
    );
  }
  if (m.role === "tool") {
    return (
      <div style={{ alignSelf: "flex-start", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--violet-200)", background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 8, padding: "8px 12px" }}>
        <span style={{ color: "var(--fg-3)", marginRight: 8 }}>⟶</span>{m.text}
      </div>
    );
  }
  return (
    <div style={{ alignSelf: "flex-start", maxWidth: "88%", fontSize: 13.5, color: "var(--fg-1)", lineHeight: 1.6, padding: "8px 4px" }}>
      {m.text}
      {m.spec && (
        <div style={{ marginTop: 14, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "12px 14px", fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-2)", lineHeight: 1.55, overflow: "hidden" }}>
          <div style={{ color: "var(--fg-3)" }}>{"{"}</div>
          <div style={{ paddingLeft: 14 }}>
            <span style={{ color: "var(--ember-500)" }}>"name"</span>: <span style={{ color: "var(--violet-200)" }}>"deep_space_population_paper"</span>,<br/>
            <span style={{ color: "var(--ember-500)" }}>"goal"</span>: <span style={{ color: "var(--violet-200)" }}>"research-paper"</span>,<br/>
            <span style={{ color: "var(--ember-500)" }}>"nodes"</span>: [scope_framer, gap_finder, thesis_architect, section_drafter, rigor_checker, revision_orchestrator],<br/>
            <span style={{ color: "var(--ember-500)" }}>"edges"</span>: [START→scope_framer→…→revision_orchestrator→END]
          </div>
          <div style={{ color: "var(--fg-3)" }}>{"}"}</div>
        </div>
      )}
    </div>
  );
}

function ChatDemo() {
  return (
    <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, overflow: "hidden", maxHeight: 560, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderBottom: "1px solid var(--border-1)", background: "var(--bg-inset)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--signal-live)", boxShadow: "0 0 6px var(--signal-live)" }} />
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)" }}>claude.ai · workflow connector attached</div>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em" }}>transcript</div>
      </div>
      <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 10, overflowY: "auto" }}>
        {TRANSCRIPT.map((m, i) => <ChatMessage key={i} m={m} />)}
      </div>
    </div>
  );
}

Object.assign(window, { ChatDemo });
