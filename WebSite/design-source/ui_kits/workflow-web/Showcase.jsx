// Showcase.jsx — deep worked example of Workflow pursuing a big goal.
// Novel-to-published. Five diagrams + honest commentary between each.

function Showcase({ onNavigate }) {
  return (
    <div>
      {/* HERO */}
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "80px 32px 48px", overflow: "hidden" }}>
        <SigilWatermark size={520} opacity={0.04} right={-140} top={-60} />
        <RitualLabel color="var(--violet-400)">· Deep example · novel → published ·</RitualLabel>
        <h1 style={{
          fontFamily: "var(--font-display)",
          fontVariationSettings: "'opsz' 144, 'SOFT' 50",
          fontSize: 60, fontWeight: 400, lineHeight: 1.1,
          letterSpacing: "-0.035em", margin: "18px 0 44px", maxWidth: 920,
        }}>
          <div>Write a sci-fi series.</div>
          <div style={{ fontStyle: "italic", fontVariationSettings: "'opsz' 144, 'SOFT' 80", color: "var(--ember-600)", marginTop: 4, paddingBottom: 16 }}>
            Actually ship it.
          </div>
        </h1>
        <p style={{ fontSize: 17, color: "var(--fg-2)", maxWidth: 760, lineHeight: 1.55, margin: "0 0 10px" }}>
          A remixed branch that combines Universe Server prose daemons, an agent crew with <code>model: inherit</code>, GraphRAG canon, git-worktree coordination, and LangGraph state control — plus two things the simple writing setup is missing: a <strong style={{ color: "var(--ember-600)" }}>mandatory self-revision gate</strong> and a <strong style={{ color: "var(--violet-200)" }}>publishing handoff</strong>.
        </p>
        <p style={{ fontSize: 13, color: "var(--fg-3)", fontStyle: "italic", maxWidth: 760, margin: "0 0 28px" }}>
          The same topology runs for research papers, investigative reporting, legal briefs. Scenes become sections; critique axes change; gates are different. The shell is the same.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Button variant="primary" onClick={() => onNavigate && onNavigate("connect")}>Fork this branch</Button>
          <Button variant="ghost" onClick={() => onNavigate && onNavigate("catalog")}>Browse other branches</Button>
        </div>
      </section>

      {/* DIAGRAM 1 — LIFECYCLE */}
      <section style={sectionStyle}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <DiagramHeading
            index="01"
            kicker="Lifecycle"
            title="The outer shell — bible to bookshelf."
            body="Five phases. Plan and Draft carry most of the interesting work; Draft is a cycle, not a step. Scenes are the atomic unit. The series bible and canon graph sit above everything as long-lived context."
          />
          <DiagramLifecycle />
        </div>
      </section>

      {/* DIAGRAM 2 — CREW */}
      <section style={sectionStyle}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <DiagramHeading
            index="02"
            kicker="Crew"
            title="Six daemons. One capability tier."
            body="The crew maps 1:1 to a standard agent lineup — scout, builder, reviewer, debugger, test-runner, planner. All use model: inherit; perspective diversity comes from prompts, not from tier-shopping. The crew reassembles per scene, not per chapter."
          />
          <DiagramCrew />
        </div>
      </section>

      {/* DIAGRAM 3 — CRITIQUE */}
      <section style={sectionStyle}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <DiagramHeading
            index="03"
            kicker="Critique gate"
            title="The bug that broke autonomous drafting."
            body="The earlier daemon never re-drafted its own weak prose. Fix: the Scribe cannot skip critique. A five-axis rubric grades every pass — voice, canon, pacing, character, prose. Failed critique is appended as context, not discarded, so the next pass targets the specific weakness. Three-cycle ceiling, then human escalation."
            accent="var(--ember-600)"
          />
          <DiagramCritique />
        </div>
      </section>

      {/* DIAGRAM 4 — CANON */}
      <section style={sectionStyle}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <DiagramHeading
            index="04"
            kicker="Canon layer"
            title="Hybrid retrieval, traceable citations."
            body="Intent routing. Multi-hop entity queries go to GraphRAG. Vibe matches go to vectors. Explicit references go straight to lookup. The synthesizer merges, reranks, and emits prompt-ready excerpts with citations back to source passages — so when continuity breaks three books in, you can trace which line shaped which."
          />
          <DiagramCanon />
        </div>
      </section>

      {/* DIAGRAM 5 — HANDOFF */}
      <section style={sectionStyle}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <DiagramHeading
            index="05"
            kicker="Handoff"
            title="Manuscript to bookshelf."
            body="Mostly deterministic. Cover + blurb is where human taste calls belong — keyword sets come for free from the canon graph. KDP covers ~90% of ebook reach; IngramSpark opens bookstore and library channels. The final outcome gate is ISBN-in-store, verified via a third-party oracle."
            accent="var(--violet-200)"
          />
          <DiagramHandoff />
        </div>
      </section>

      {/* HOW IT DROPS IN */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <RitualLabel>How it drops into your kit</RitualLabel>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 40, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 28px", maxWidth: 820 }}>
            State in LangGraph. Branches in worktrees. Canon in Graph + vector.
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {[
              ["State", "Scene is a node. Chapter is a subgraph. Book is the outer graph. Series bible is long-lived context. Standard LangGraph."],
              ["Worktrees", "Each scene gets a git worktree. BRANCH_INTENT.md names the plan. status.md tracks critique passes. plan.md holds the assembled prompt."],
              ["Triage", "Scenes that fail three critique cycles follow the orphaned-branch protocol — escalated out of the daemon for human attention, not silently dropped."],
              ["Cross-goal reuse", "The scene loop here is the same topology as a research paper's section loop: draft → critique → revise → commit. Fixes to one branch propagate to both."],
            ].map(([t, body], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "22px 24px" }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, color: "var(--fg-1)", letterSpacing: "-0.01em", marginBottom: 8 }}>{t}</div>
                <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>{body}</p>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 32, background: "var(--bg-inset)", border: "1px dashed var(--border-2)", borderRadius: 12, padding: "20px 24px" }}>
            <RitualLabel color="var(--violet-400)">Realistic first cut</RitualLabel>
            <p style={{ fontSize: 14, color: "var(--fg-2)", lineHeight: 1.6, margin: "10px 0 0", maxWidth: 820 }}>
              Implement the critique gate in the existing daemon first — where the self-revision bug actually bit. Validate it produces better prose. Then port the pattern into a new universe. Publishing stays manual for book one; you'll learn what needs automating from doing it by hand once.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
          <div style={{ maxWidth: 640 }}>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: "0 0 10px" }}>
              Your pipeline doesn't have to look like this.
            </h3>
            <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.55, margin: 0 }}>
              This is one branch of <code>fantasy-novel</code>. Fork it, strip nodes out, add your own. Or start from scratch and bind to whichever goal fits. Your chatbot will help you assemble the spec.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="primary" size="lg" onClick={() => onNavigate && onNavigate("connect")}>Add the connector</Button>
            <Button variant="ghost" size="lg" onClick={() => onNavigate && onNavigate("catalog")}>Browse goals</Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function DiagramHeading({ index, kicker, title, body, accent }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 24, marginBottom: 24, alignItems: "start" }}>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 80, fontWeight: 400, color: accent || "var(--fg-4)", lineHeight: 0.9, fontVariationSettings: "'opsz' 144, 'SOFT' 100", letterSpacing: "-0.04em" }}>
        {index}
      </div>
      <div>
        <RitualLabel color={accent || "var(--violet-400)"}>· {kicker} ·</RitualLabel>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: 34, fontWeight: 500, letterSpacing: "-0.02em", margin: "10px 0 12px", textWrap: "balance" }}>
          {title}
        </h2>
        <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0, maxWidth: 820 }}>{body}</p>
      </div>
    </div>
  );
}

const sectionStyle = {
  borderTop: "1px solid var(--border-1)",
  padding: "72px 32px",
};

Object.assign(window, { Showcase });
