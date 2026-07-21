// AgentTeams.jsx — "How Claude Code Agent Teams work" deep-dive page.
// Uses the 10 canonical diagrams in timestamp order. Each gets a sidebar framing.

const DIAGRAMS = [
  {
    n: "01",
    src: "../../assets/teams/01-node-lifecycle.png",
    title: "A single node's lifecycle",
    lead: "Every agent in every team shape follows the same 6-state loop. Understanding this one loop explains the whole system.",
    bullets: [
      ["Idle is the default.", "A 20-agent team with 3 active nodes is burning tokens for 3, not 20. The rest are listening, not thinking."],
      ["Edges are triggers.", "An inbound edge fires the moment an upstream node writes this node's input field — not on a timer, not on a schedule."],
      ["Working is the only billable state.", "Everything else is bookkeeping. A Claude Code session is spawned, does work, writes output, dies."],
    ],
    callout: { label: "Key insight", body: "The team is event-driven from the data. No central scheduler decides who runs — the state graph does." },
    accent: "var(--ember-600)",
  },
  {
    n: "02",
    src: "../../assets/teams/02-three-node-annotated.png",
    title: "3-node team, fully annotated",
    lead: "The smallest useful team: lead → dev → checker. Every trigger, state field, and gate decision made visible.",
    bullets: [
      ["Solid arrows are automatic.", "They fire via state-write triggers — upstream node wrote, downstream daemon spawns. No orchestrator touches them."],
      ["Dashed arrows are orchestrated.", "The loop-back after a gate decision is interpreted by the outer runner. That's the one place a higher authority intervenes."],
      ["Gate emits a decision string.", "'END', 'LOOP_TO: lead', 'SOFT_ESCALATE: reason' — structured, machine-readable, not free text."],
    ],
    callout: { label: "This distinction matters", body: "Forward pass is pure data-flow. The loop-back requires an orchestrator one level up. That's BUG-003 manifesting as an architecture choice." },
    accent: "var(--violet-400)",
  },
  {
    n: "03",
    src: "../../assets/teams/03-gate-routing.png",
    title: "Gate routing · the failure-class matrix",
    lead: "Every variant's gate has the same shape: read check_result, classify, route. What changes between variants is the resolution of the routing — how many distinct failure classes the team can diagnose.",
    bullets: [
      ["3-node gate · 4 classes.", "PASS / FAIL_PLAN / FAIL_IMPL / FAIL_TEST / FAIL_UNCLEAR."],
      ["5-node gate · 5 classes.", "A finer-grained lead fallback for unclear failures."],
      ["10-node gate · 9 classes.", "Research, architecture, plan, frontend, backend, db, review failures — each get their own route."],
    ],
    callout: { label: "The pattern", body: "Higher resolution = more precise retry routing = fewer wasted iterations. Resolution doubles with each tier." },
    accent: "var(--signal-idle)",
  },
  {
    n: "04",
    src: "../../assets/teams/04-gate-resolution-tiers.png",
    title: "20-node gate · 18 failure classes",
    lead: "At production scale the gate reaches near-atomic resolution. Fail on a migration? Route straight to migration_writer. Fail a security test? Route to security_reviewer. No more 'try the whole thing again.'",
    bullets: [
      ["Resolution doubles with each tier.", "3-node = 4 classes · 5-node = 5 · 10-node = 9 · 20-node = 18."],
      ["Higher resolution = less wasted work.", "A failed unit test doesn't trigger a re-plan — it triggers exactly the one node that writes unit tests."],
      ["The gate never loops itself.", "It emits a decision. The outer runner does the actual looping. This keeps the gate a pure classifier."],
    ],
    callout: { label: "Why it scales", body: "Each new tier doesn't rewrite the gate — it adds specialization in the failure-class vocabulary. The invariant is the same." },
    accent: "var(--ember-500)",
  },
  {
    n: "05",
    src: "../../assets/teams/05-parallel-zones.png",
    title: "Parallel execution zones",
    lead: "3-node and 5-node teams are pure serial chains — only one node active at a time. At 10-node, parallelism kicks in. This diagram highlights which nodes fire simultaneously.",
    bullets: [
      ["Fan-out edges mean concurrent.", "researcher and architect both read from lead and run at the same time."],
      ["Fan-in edges mean barrier.", "planner waits for BOTH researcher AND architect — the trigger is 'all three of my input fields populated,' not 'any one of them.'"],
      ["Parallelism is graph-topology, not an execution mode.", "There's no 'parallel' flag. If the DAG fans out, the daemons fan out."],
    ],
    callout: { label: "Where time drops", body: "Discovery becomes max(researcher, architect) instead of the sum. Implementation becomes max(fe, be, db). ~60% wall-clock reduction in practice." },
    accent: "var(--violet-200)",
  },
  {
    n: "06",
    src: "../../assets/teams/06-twenty-node-production.png",
    title: "20-node production team with execution bands",
    lead: "The full production topology. Each vertical band runs its phase; parallel zones inside bands light up simultaneously. Two parallel chains inside the quality band — tests fan in sequentially, reviews fan in sequentially, then both flow into debugger which synthesizes everything before checker judges.",
    bullets: [
      ["Bands = phases.", "discovery · planning · implementation · quality · finalize. Each band has its own internal topology."],
      ["Quality is two chains.", "Tests (unit → integ → e2e) and reviews (code → sec → perf) run simultaneously. They converge at debugger."],
      ["checker is the final judge.", "It reads everything — implementation, tests, reviews, debugger output — and emits the gate decision."],
    ],
    callout: { label: "Same invariants, more specialization", body: "Nothing about the gate, triggers, or node lifecycle changed from 3-node. Only the role vocabulary expanded." },
    accent: "var(--ember-600)",
  },
  {
    n: "07",
    src: "../../assets/teams/07-execution-timeline-and-iteration.png",
    title: "Execution timeline + the iteration loop",
    lead: "Gantt-style view of a 10-node run, plus the loop mechanic that makes 'build until done' actually run. The gate doesn't loop inside the workflow — it emits a decision string the outer runner interprets.",
    bullets: [
      ["Parallelism shaves ~60% off wall-clock.", "Discovery max(researcher, architect) = 12s instead of 22s. Quality max(tester, reviewer) = 15s instead of 27s."],
      ["Token cost is unchanged.", "Each daemon runs once, regardless of whether it ran concurrently with others. Parallelism buys latency, not tokens."],
      ["State is preserved between loops.", "Only fields downstream of the failing node are cleared. Upstream work survives — a researcher's findings don't get discarded when a dev retries."],
    ],
    callout: { label: "Three mechanics that make this autonomous", body: "Forward pass is deterministic · gate decision is structured · state is preserved across retries. Together: build-until-done without a human loop." },
    accent: "var(--signal-live)",
  },
  {
    n: "08",
    src: "../../assets/teams/08-four-variants-side-by-side.png",
    title: "Four variants scale side-by-side",
    lead: "Same flow, three resolutions of specialization. Watch how roles split as you scale.",
    bullets: [
      ["3 → 5 · split the monolithic dev.", "Plan + implement + test, separated. The lead stops context-switching."],
      ["5 → 10 · parallelize discovery and implementation.", "Researcher + architect. Frontend + backend + db dev. 3x wall-clock improvement on the critical path."],
      ["10 → 20 · split review and testing axes.", "Security, performance, unit, integration, e2e each get their own specialist. Adds a delivery pipeline on the tail."],
    ],
    callout: { label: "The scaling rule", body: "Each split targets the role most likely to be the bottleneck at that size. Scaling is not 'add agents' — it's 'split the one that's blocking.'" },
    accent: "var(--violet-400)",
  },
  {
    n: "09",
    src: "../../assets/teams/09-trigger-summary.png",
    title: "Trigger summary per variant",
    lead: "Every node in every variant uses this exact trigger pattern. A parallel-zone node (like tester in the 10-node team) just has more input fields feeding its T2 decision — it waits for 3 instead of 1.",
    bullets: [
      ["The loop is invariant.", "Upstream wrote my input field → check if all required inputs are populated → if yes, daemon spawns with subagent definition → work completes → output fields written → downstream nodes re-evaluate their own T2."],
      ["No central scheduler required.", "Each node decides independently whether to fire. The graph's shape is the schedule."],
      ["Parallel zones = multiple inputs, single trigger.", "Adding parallelism doesn't add machinery — it adds input fields."],
    ],
    callout: { label: "Why this composes", body: "A team of 3 and a team of 300 use the same primitive. The only thing that changes is how many nodes and how many input fields each has." },
    accent: "var(--signal-idle)",
  },
  {
    n: "10",
    src: "../../assets/teams/10-through-line.png",
    title: "The through-line",
    lead: "Everything above reduces to seven principles. Read them together and the whole system collapses into one pattern.",
    bullets: [
      ["Nodes are idle by default.", "Tokens are only spent when WORKING (diagram 1)."],
      ["Edges are triggers, not schedules.", "A node fires when its upstream writes its input fields (diagrams 2, 9)."],
      ["Parallelism is graph-topology, not an execution mode.", "Fan-out means concurrent; fan-in means barrier (diagrams 4, 5)."],
      ["The gate is a classifier, not a valve.", "It emits routing decisions; an outer runner does the actual looping (diagram 7)."],
      ["Scaling adds specialization to the failure-class vocabulary.", "More nodes = finer gate resolution = more precise retries (diagram 3)."],
      ["Every variant is the same pattern, different resolution.", "lead → produce → verify → route is the invariant (diagram 8)."],
    ],
    callout: { label: "Read it once from the top", body: "Every team you'll ever build on Workflow is a composition of these seven rules. Chat with your chatbot, redesign the team, the rules don't change." },
    accent: "var(--ember-600)",
  },
];

function AgentTeams({ onNavigate }) {
  return (
    <div>
      {/* HERO */}
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "80px 32px 56px", overflow: "hidden" }}>
        <SigilWatermark size={620} opacity={0.05} right={-180} bottom={-180} />
        <div style={{ position: "relative", maxWidth: 820 }}>
          <RitualLabel color="var(--violet-400)">· Claude Code Agent Teams · the full mechanism ·</RitualLabel>
          <h1 style={{
            fontFamily: "var(--font-display)",
            fontVariationSettings: "'opsz' 144, 'SOFT' 50",
            fontSize: 80, fontWeight: 400, lineHeight: 0.96,
            letterSpacing: "-0.035em", margin: "22px 0 22px", textWrap: "balance",
          }}>
            <div>Ten diagrams.</div>
            <div style={{
              fontStyle: "italic",
              fontVariationSettings: "'opsz' 144, 'SOFT' 80",
              color: "var(--ember-600)",
              paddingBottom: 8,
            }}>
              One engine.
            </div>
          </h1>
          <p style={{ fontSize: 17, color: "var(--fg-2)", lineHeight: 1.55, margin: "0 0 18px", maxWidth: 720 }}>
            What actually happens when you tell your chatbot "spin up a team and build this"? Start with a single node. End with a 20-agent production topology. Every layer is the same pattern at a different resolution.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {["node lifecycle", "gate routing", "parallel zones", "execution bands", "iteration loop", "trigger pattern"].map((t, i) => (
              <span key={i} style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em", background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 4, padding: "5px 9px" }}>
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* QUICK NAV */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "28px 32px", background: "var(--bg-0)", position: "sticky", top: 57, zIndex: 20, backdropFilter: "blur(8px)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <RitualLabel>Jump to</RitualLabel>
          {DIAGRAMS.map((d) => (
            <a key={d.n} href={`#d-${d.n}`} style={{
              fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-2)",
              textTransform: "uppercase", letterSpacing: "0.12em",
              background: "var(--bg-2)", border: "1px solid var(--border-1)",
              padding: "5px 9px", borderRadius: 4, textDecoration: "none",
              transition: "all 140ms",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = d.accent; e.currentTarget.style.borderColor = d.accent; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--fg-2)"; e.currentTarget.style.borderColor = "var(--border-1)"; }}
            >
              {d.n}
            </a>
          ))}
        </div>
      </section>

      {/* DIAGRAM WALKTHROUGH */}
      {DIAGRAMS.map((d, i) => (
        <DiagramBlock key={d.n} diagram={d} index={i} />
      ))}

      {/* CTA TAIL */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "64px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 40, alignItems: "center" }}>
          <div>
            <RitualLabel color="var(--ember-500)">· You've read the engine ·</RitualLabel>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: 44, fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.05, margin: "14px 0 16px", textWrap: "balance" }}>
              Now command one from your phone.
            </h2>
            <p style={{ fontSize: 15.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 24px", maxWidth: 560 }}>
              Every agent you just saw — lead, planner, researcher, tester, checker, gate — is a summonable daemon. You compose them by chatting with any MCP-capable chatbot. The team reshapes as you talk.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button variant="primary" size="lg" onClick={() => onNavigate("connect")}>
                Add the connector <span style={{ fontFamily: "var(--font-mono)", opacity: 0.8 }}>→</span>
              </Button>
              <Button variant="secondary" size="lg" onClick={() => onNavigate("host")}>Summon a daemon</Button>
              <Button variant="ghost" size="lg" onClick={() => onNavigate("contribute")}>Vibe-code with us</Button>
            </div>
          </div>
          <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "22px 24px" }}>
            <RitualLabel color="var(--violet-400)">· Recap · the invariant ·</RitualLabel>
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10, fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.55 }}>
              <div><span style={{ color: "var(--ember-600)" }}>lead</span> → <span style={{ color: "var(--violet-400)" }}>produce</span> → <span style={{ color: "var(--signal-idle)" }}>verify</span> → <span style={{ color: "var(--signal-live)" }}>route</span></div>
              <div style={{ color: "var(--fg-3)" }}>Every team. Any size. One pattern.</div>
              <div style={{ color: "var(--fg-3)" }}>3 agents or 300 — same rules apply.</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/* ---------- One diagram block ---------- */
function DiagramBlock({ diagram, index }) {
  const d = diagram;
  const altBg = index % 2 === 1;
  return (
    <section id={`d-${d.n}`} style={{
      borderTop: "1px solid var(--border-1)",
      padding: "72px 32px",
      background: altBg ? "var(--bg-0)" : "transparent",
      scrollMarginTop: 120,
    }}>
      <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gridTemplateColumns: "auto 1fr", gap: 48, alignItems: "start" }}>
        {/* LEFT: image */}
        <div>
          <div style={{
            background: "var(--bg-2)",
            border: "1px solid var(--border-1)",
            borderRadius: 14,
            padding: 16,
            boxShadow: "0 20px 40px -20px rgba(0,0,0,0.5)",
          }}>
            <img
              src={d.src}
              alt={d.title}
              style={{ display: "block", width: 420, height: "auto", borderRadius: 6, background: "#fff" }}
            />
          </div>
          <div style={{ marginTop: 10, fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em", textAlign: "center" }}>
            Diagram {d.n} · captured from the source conversation
          </div>
        </div>

        {/* RIGHT: framing */}
        <div style={{ paddingTop: 4 }}>
          <div style={{ marginBottom: 14 }}>
            <div style={{
              fontFamily: "var(--font-display)",
              fontVariationSettings: "'opsz' 144, 'SOFT' 50",
              fontSize: 64, fontWeight: 400, letterSpacing: "-0.04em",
              color: d.accent, lineHeight: 1, marginBottom: 10,
            }}>{d.n}</div>
            <RitualLabel color={d.accent}>· Diagram {parseInt(d.n)} of 10 ·</RitualLabel>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: "10px 0 0", lineHeight: 1.15, textWrap: "balance", paddingBottom: 6 }}>
              {d.title}
            </h3>
          </div>

          <p style={{ fontSize: 16, color: "var(--fg-2)", lineHeight: 1.6, margin: "18px 0 24px", maxWidth: 620 }}>
            {d.lead}
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}>
            {d.bullets.map(([t, body], i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "24px 1fr", gap: 14, alignItems: "baseline" }}>
                <div style={{
                  width: 22, height: 22, borderRadius: "50%",
                  background: "transparent",
                  border: `1.5px solid ${d.accent}`,
                  color: d.accent, fontFamily: "var(--font-mono)",
                  fontSize: 11, fontWeight: 600, display: "flex",
                  alignItems: "center", justifyContent: "center",
                  marginTop: 2,
                }}>{i + 1}</div>
                <div>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 500, color: "var(--fg-1)", letterSpacing: "-0.005em", marginBottom: 2 }}>
                    {t}
                  </div>
                  <div style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.55 }}>
                    {body}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div style={{
            background: "var(--bg-2)",
            border: `1px solid ${d.accent}44`,
            borderLeft: `3px solid ${d.accent}`,
            borderRadius: 8,
            padding: "14px 18px",
            maxWidth: 620,
          }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: d.accent, textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 6, fontWeight: 600 }}>
              {d.callout.label}
            </div>
            <div style={{ fontSize: 13.5, color: "var(--fg-1)", lineHeight: 1.55, fontStyle: "italic" }}>
              {d.callout.body}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

Object.assign(window, { AgentTeams });
