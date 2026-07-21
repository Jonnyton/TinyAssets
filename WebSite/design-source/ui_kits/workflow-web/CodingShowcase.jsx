// CodingShowcase.jsx — the second deep vertical. Parallel to Novel.
// Tier-aware: same shell, higher resolution on failure classes as you scale.

function CodingShowcase({ onNavigate }) {
  return (
    <div>
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "80px 32px 48px" }}>
        <SigilWatermark size={520} opacity={0.04} right={-140} top={-60} />
        <RitualLabel color="var(--violet-400)">· Deep example · ship working software ·</RitualLabel>
        <h1 style={{
          fontFamily: "var(--font-display)",
          fontVariationSettings: "'opsz' 144, 'SOFT' 50",
          fontSize: 60, fontWeight: 400, lineHeight: 1.1,
          letterSpacing: "-0.035em", margin: "18px 0 44px", maxWidth: 920,
        }}>
          <div>Build software autonomously.</div>
          <div style={{ fontStyle: "italic", fontVariationSettings: "'opsz' 144, 'SOFT' 80", color: "var(--ember-600)", marginTop: 4, paddingBottom: 16 }}>
            The team sizes itself.
          </div>
        </h1>
        <p style={{ fontSize: 17, color: "var(--fg-2)", maxWidth: 760, lineHeight: 1.55, margin: "0 0 10px" }}>
          Coding is a goal with a deep branch catalog. Three-node for a bug fix. Five-node for a feature. Ten-node for a subsystem. Twenty-node for a production project. <strong style={{ color: "var(--ember-600)" }}>Same invariant</strong> — lead → produce → verify → route — just scaled to the failure surface.
        </p>
        <p style={{ fontSize: 13, color: "var(--fg-3)", fontStyle: "italic", maxWidth: 760, margin: "0 0 28px" }}>
          This page walks the mechanism. The same mechanism runs novels, papers, briefs — the variable is what <em>produce</em> and <em>verify</em> mean for your goal.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Button variant="primary" onClick={() => onNavigate?.("connect")}>Fork the 10-node</Button>
          <Button variant="ghost" onClick={() => onNavigate?.("showcase")}>See the Novel example</Button>
        </div>
      </section>

      <section style={codingSection}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <CodingHeading index="01" kicker="Node lifecycle" title="Idle is free. Working is the only expensive state." body="Every node in every tier follows the same lifecycle. Understanding this one loop explains the whole system. A node sits in IDLE until an upstream write fires its trigger; it only burns tokens inside WORKING." />
          <DiagCodingLifecycle />
        </div>
      </section>

      <section style={codingSection}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <CodingHeading index="02" kicker="Scaling tiers" title="Pick your tier. The branch scales to the failure surface." body="3-node for a bug; 20-node for a launch. Each tier splits the band most likely to bottleneck at that size. 3→5 splits dev into plan+impl+test. 5→10 parallelizes discovery and implementation. 10→20 adds review axes and a delivery pipeline." />
          <DiagCodingTiers />
        </div>
      </section>

      <section style={codingSection}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <CodingHeading index="03" kicker="Gate routing" title="The gate is a classifier, not a valve." accent="var(--ember-600)" body="The gate reads check_result and emits a decision string. The outer runner pattern-matches it on the next invocation. Resolution doubles per tier: 3-node gate distinguishes 4 failure classes, 20-node distinguishes 18 — finer classification means more precise retry routing and fewer wasted cycles." />
          <DiagCodingGate />
        </div>
      </section>

      <section style={codingSection}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <CodingHeading index="04" kicker="Parallel zones" title="Fan-out is free. Fan-in is a barrier." body="At 10-node and above, parallelism kicks in. planner waits for both researcher and architect; tester waits for all three *_dev lanes. Wall-clock drops ~60% vs serial. Token cost stays the same — each daemon runs independently." />
          <DiagCodingParallel />
        </div>
      </section>

      <section style={codingSection}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <CodingHeading index="05" kicker="Iteration loop" title="'Build until done' is the outer runner's job." accent="var(--violet-200)" body="The gate doesn't loop inside the workflow — it emits a decision and an outer runner interprets it. Forward pass is deterministic. State is preserved across loops: only fields downstream of the failing node are cleared. Upstream work is never discarded." />
          <DiagCodingIteration />
        </div>
      </section>

      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <RitualLabel>The through-line</RitualLabel>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 36, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 28px", maxWidth: 820 }}>
            Read these diagrams top-down.
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {[
              ["Nodes are idle by default.", "Tokens only spent when WORKING. A team of 20 with 3 active nodes bills for 3."],
              ["Edges are triggers, not schedules.", "A node fires when its upstream writes its input field. No scheduler, no polling."],
              ["Parallelism is graph topology.", "Fan-out edges mean concurrent. Fan-in edges mean barrier. Same DAG controls both."],
              ["The gate is a classifier.", "Emits a string; an outer runner does the looping. Loop-back is state-preserving, not state-resetting."],
              ["Scaling adds specialization.", "More nodes → finer gate resolution → more precise retries. The invariant doesn't change."],
              ["Same pattern, different goal.", "Swap 'dev' for 'scribe', 'tester' for 'beta reader', 'deploy' for 'publish'. Topology is identical."],
            ].map(([t, body], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "22px 24px" }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 20, fontWeight: 500, color: "var(--fg-1)", letterSpacing: "-0.01em", marginBottom: 8 }}>{t}</div>
                <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
          <div style={{ maxWidth: 640 }}>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: 30, fontWeight: 500, letterSpacing: "-0.02em", margin: "0 0 10px" }}>
              Any goal. Pick a tier.
            </h3>
            <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.55, margin: 0 }}>
              Coding is one example. The same mechanism runs any goal you can describe to your chatbot.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="primary" size="lg" onClick={() => onNavigate?.("catalog")}>Browse goals</Button>
            <Button variant="ghost" size="lg" onClick={() => onNavigate?.("connect")}>Add the connector</Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function CodingHeading({ index, kicker, title, body, accent }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 24, marginBottom: 24, alignItems: "start" }}>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 80, fontWeight: 400, color: accent || "var(--fg-4)", lineHeight: 0.9, fontVariationSettings: "'opsz' 144, 'SOFT' 100", letterSpacing: "-0.04em" }}>
        {index}
      </div>
      <div>
        <RitualLabel color={accent || "var(--violet-400)"}>· {kicker} ·</RitualLabel>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: "10px 0 12px" }}>
          {title}
        </h2>
        <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0, maxWidth: 820 }}>{body}</p>
      </div>
    </div>
  );
}

const codingSection = { borderTop: "1px solid var(--border-1)", padding: "72px 32px" };

Object.assign(window, { CodingShowcase });
