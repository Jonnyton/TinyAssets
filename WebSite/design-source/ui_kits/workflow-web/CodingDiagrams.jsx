// CodingDiagrams.jsx — diagrams for the Coding showcase.
// Reuses FlowNode/Arrow/Legend/FlowGroup from Diagrams.jsx.

// Palette per transcript: lead(blue) · producer(green) · quality(amber) · gate(orange) · delivery(violet)
const C = {
  lead:     { fill: "rgba(58, 88, 168, 0.22)", stroke: "rgba(108, 148, 228, 0.6)", text: "var(--fg-1)", meta: "#a7c0f2" },
  producer: { fill: "rgba(109, 211, 166, 0.16)", stroke: "rgba(109, 211, 166, 0.55)", text: "var(--fg-1)", meta: "var(--signal-live)" },
  quality:  { fill: "rgba(241, 194, 86, 0.14)", stroke: "rgba(241, 194, 86, 0.55)", text: "var(--fg-1)", meta: "var(--signal-idle)" },
  gate:     { fill: "rgba(233, 147, 69, 0.18)", stroke: "rgba(233, 147, 69, 0.6)", text: "var(--fg-1)", meta: "#f0a86a" },
  delivery: { fill: "rgba(138, 99, 206, 0.2)", stroke: "rgba(138, 99, 206, 0.6)", text: "var(--fg-1)", meta: "var(--violet-200)" },
  idle:     { fill: "var(--bg-3)", stroke: "var(--border-2)", text: "var(--fg-2)", meta: "var(--fg-3)" },
  accent:   { fill: "rgba(233, 69, 96, 0.14)", stroke: "var(--ember-600)", text: "var(--fg-1)", meta: "var(--ember-500)" },
};

function CNode({ title, sub, tone = "idle", width = 150, code = false }) {
  const t = C[tone];
  return (
    <div style={{
      background: t.fill, border: `1px solid ${t.stroke}`, borderRadius: 8,
      padding: "10px 12px", width, textAlign: "center",
    }}>
      <div style={{
        fontFamily: code ? "var(--font-mono)" : "var(--font-sans)",
        fontSize: 12.5, fontWeight: 600, color: t.text, marginBottom: sub ? 3 : 0, lineHeight: 1.2,
      }}>{title}</div>
      {sub && <div style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, color: t.meta, lineHeight: 1.35 }}>{sub}</div>}
    </div>
  );
}

const cFrame = {
  background: "var(--bg-2)", border: "1px solid var(--border-1)",
  borderRadius: 14, padding: "32px 28px 24px",
};

function CLegend() {
  const items = [
    ["lead", "Coordinator"], ["producer", "Producer"], ["quality", "Quality"], ["gate", "Gate"], ["delivery", "Delivery"],
  ];
  return (
    <div style={{ display: "flex", gap: 18, marginTop: 20, paddingTop: 14, borderTop: "1px solid var(--border-1)", flexWrap: "wrap", justifyContent: "center" }}>
      {items.map(([k, label]) => (
        <div key={k} style={{ display: "flex", alignItems: "center", gap: 7, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: C[k].fill, border: `1px solid ${C[k].stroke}` }} />
          {label}
        </div>
      ))}
    </div>
  );
}

// ---------- 1 · Node lifecycle ----------
function DiagCodingLifecycle() {
  const states = [
    { title: "IDLE", sub: "no inbound trigger", tone: "idle" },
    { title: "TRIGGERED", sub: "input field written", tone: "lead" },
    { title: "DAEMON_SPAWN", sub: "inherits subagent def", tone: "producer" },
    { title: "WORKING", sub: "tokens spent here", tone: "accent" },
    { title: "WRITING_HANDOFF", sub: "writes output keys", tone: "quality" },
    { title: "FAN_OUT", sub: "signals downstream", tone: "delivery" },
  ];
  return (
    <div style={cFrame}>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
        {states.map((s, i) => (
          <React.Fragment key={s.title}>
            <CNode {...s} width={150} />
            {i < states.length - 1 && <div style={{ color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>→</div>}
          </React.Fragment>
        ))}
      </div>
      <div style={{ marginTop: 18, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        Only <span style={{ color: "var(--ember-500)" }}>WORKING</span> burns tokens. IDLE is free. A team of 20 with 3 active nodes bills for 3.
      </div>
      <CLegend />
    </div>
  );
}

// ---------- 2 · Scaling tiers side-by-side ----------
function DiagCodingTiers() {
  const tiers = [
    { size: "3", label: "monolith dev", cols: [[["lead", "lead"]], [["producer", "dev"]], [["quality", "checker"]], [["gate", "gate"]]] },
    { size: "5", label: "split plan + test", cols: [[["lead", "lead"]], [["producer", "planner"], ["producer", "dev"]], [["quality", "tester"], ["quality", "checker"]], [["gate", "gate"]]] },
    { size: "10", label: "parallel zones", cols: [[["lead", "lead"]], [["producer", "researcher"], ["producer", "architect"], ["producer", "planner"]], [["producer", "FE dev"], ["producer", "BE dev"], ["producer", "DB dev"]], [["quality", "tester"], ["quality", "reviewer"], ["quality", "checker"]], [["gate", "gate"], ["delivery", "docs"]]] },
    { size: "20", label: "full production", cols: [[["lead", "lead"]], [["producer", "research ×3"], ["producer", "plan + risk"]], [["producer", "impl ×5"]], [["quality", "test ×3"], ["quality", "review ×3"], ["quality", "debugger"]], [["quality", "checker"], ["gate", "gate"], ["delivery", "docs + deploy"]]] },
  ];
  return (
    <div style={cFrame}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {tiers.map((t) => (
          <div key={t.size} style={{ background: "var(--bg-3)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "18px 18px 14px" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, color: "var(--fg-1)", letterSpacing: "-0.02em" }}>{t.size}<span style={{ fontSize: 13, color: "var(--fg-3)", fontWeight: 400, marginLeft: 4 }}>-node</span></div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>{t.label}</div>
            </div>
            <div style={{ display: "flex", gap: 5, alignItems: "stretch" }}>
              {t.cols.map((col, i) => (
                <React.Fragment key={i}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
                    {col.map(([tone, label], j) => (
                      <CNode key={j} title={label} tone={tone} width="100%" />
                    ))}
                  </div>
                  {i < t.cols.length - 1 && <div style={{ color: "var(--fg-4)", display: "flex", alignItems: "center", fontFamily: "var(--font-mono)", fontSize: 11 }}>→</div>}
                </React.Fragment>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 16, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        Same invariant at every tier: <span style={{ color: "var(--fg-2)" }}>lead → produce → verify → route</span>. Tiers split the band most likely to bottleneck.
      </div>
      <CLegend />
    </div>
  );
}

// ---------- 3 · Gate classifier / retry ----------
function DiagCodingGate() {
  return (
    <div style={cFrame}>
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <CNode title="check_result" sub="artifact classification" tone="quality" width={170} />
        <div style={{ color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>→</div>
        <CNode title="gate" sub="emits decision" tone="gate" width={170} />
      </div>
      <div style={{ height: 28 }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        <CNode title="PASS" sub="→ END" tone="delivery" width="100%" />
        <CNode title={`LOOP_TO: <node>`} sub="preserve upstream, clear downstream, retry_count++" tone="producer" width="100%" />
        <CNode title="SOFT_ESCALATE" sub="decompose task · reset retry_count" tone="quality" width="100%" />
        <CNode title="FAIL_UNCLEAR" sub="flag for human" tone="accent" width="100%" />
      </div>
      <div style={{ marginTop: 16, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        The gate is a classifier, not a valve. It emits a string; the outer runner interprets it on the next run.<br/>
        Tier resolution: 3-node = 4 classes · 5-node = 5 · 10-node = 9 · 20-node = 18.
      </div>
    </div>
  );
}

// ---------- 4 · Parallel zones ----------
function DiagCodingParallel() {
  return (
    <div style={cFrame}>
      <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", rowGap: 14, columnGap: 16, alignItems: "center" }}>
        {[
          ["SERIAL · lead", [["lead", "lead"]]],
          ["PARALLEL · discover", [["producer", "researcher"], ["producer", "architect"]]],
          ["SERIAL · plan", [["producer", "planner"]]],
          ["PARALLEL · implement", [["producer", "FE dev"], ["producer", "BE dev"], ["producer", "DB dev"]]],
          ["PARALLEL · quality", [["quality", "tester"], ["quality", "reviewer"]]],
          ["SERIAL · synthesize", [["quality", "checker"], ["gate", "gate"], ["delivery", "docs"]]],
        ].map(([label, nodes], i) => (
          <React.Fragment key={i}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em", textAlign: "right" }}>
              {label}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {nodes.map(([tone, name], j) => (
                <CNode key={j} title={name} tone={tone} width={140} />
              ))}
            </div>
          </React.Fragment>
        ))}
      </div>
      <div style={{ marginTop: 18, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        Fan-in barrier: planner waits for <em>both</em> researcher <em>and</em> architect — trigger is "all inputs populated."<br/>
        Parallelism shaves ~60% wall-clock off a 10-node run; token cost is unchanged.
      </div>
      <CLegend />
    </div>
  );
}

// ---------- 5 · Iteration loop ----------
function DiagCodingIteration() {
  const steps = [
    ["User / Cron", "start project (brief + criteria)", "lead"],
    ["Outer runner", "init state · retry_count=0", "lead"],
    ["Branch", "run_branch(inputs) · forward pass", "producer"],
    ["Gate node", "write gate_decision", "gate"],
    ["Outer runner", "parse decision", "lead"],
    ["Branch", "on LOOP_TO: preserve state, clear downstream, retry", "producer"],
    ["State", "on SOFT_ESCALATE: decompose task, reset retry", "quality"],
    ["State", "on END: deliverable — docs + deploy", "delivery"],
  ];
  return (
    <div style={cFrame}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {steps.map(([actor, msg, tone], i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "40px 140px 1fr", gap: 14, alignItems: "center" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textAlign: "right" }}>{String(i + 1).padStart(2, "0")}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: C[tone].meta, textTransform: "uppercase", letterSpacing: "0.1em" }}>{actor}</div>
            <CNode title={msg} tone={tone} width="100%" />
          </div>
        ))}
      </div>
      <div style={{ marginTop: 16, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textAlign: "center", fontStyle: "italic" }}>
        State is preserved across loops. A researcher's findings don't get discarded when a dev retries.
      </div>
    </div>
  );
}

Object.assign(window, { DiagCodingLifecycle, DiagCodingTiers, DiagCodingGate, DiagCodingParallel, DiagCodingIteration });
