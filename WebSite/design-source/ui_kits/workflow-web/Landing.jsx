// Landing.jsx — rewritten. Tone: engineer's tool, ritual aesthetics on top.
// Lead beat: show the actual chat interaction + the DAG it produces.

function Landing({ onNavigate }) {
  return (
    <div>
      {/* HERO */}
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "100px 32px 72px", overflow: "hidden" }}>
        <SigilWatermark size={620} opacity={0.05} right={-160} bottom={-200} />
        <div style={{ position: "relative", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 56, alignItems: "center" }}>
          <div>
            <RitualLabel color="var(--violet-400)">· Command a Claude Code Agent Team from your phone ·</RitualLabel>
            <h1 style={{
              fontFamily: "var(--font-display)",
              fontVariationSettings: "'opsz' 144, 'SOFT' 50",
              fontSize: 84, fontWeight: 400, lineHeight: 0.95,
              letterSpacing: "-0.035em", margin: "22px 0 20px", textWrap: "balance",
            }}>
              <div>Design, run, and redesign</div>
              <div style={{
                fontStyle: "italic",
                fontVariationSettings: "'opsz' 144, 'SOFT' 80",
                color: "var(--ember-600)",
                paddingBottom: 8,
              }}>
                agent teams from chat.
              </div>
            </h1>
            <p style={{ fontSize: 17, lineHeight: 1.5, color: "var(--fg-2)", margin: "0 0 10px" }}>
              Any chatbot. Any device. An MCP connection turns your phone into mission control for a legion of Claude Code daemons — spawn them, retool them, branch them, kill them. All from the thread you're already in.
            </p>
            <p style={{ fontSize: 14, color: "var(--fg-3)", margin: "0 0 32px", fontStyle: "italic" }}>
              Research papers. Novels. Reporting. Legal briefs. A team of one daemon, or a hundred — you decide.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button variant="primary" size="lg" onClick={() => onNavigate("connect")}>
                Add the connector <span style={{ fontFamily: "var(--font-mono)", opacity: 0.8, marginLeft: 4 }}>→</span>
              </Button>
              <Button variant="secondary" size="lg" onClick={() => onNavigate("host")}>
                Summon a daemon
              </Button>
              <Button variant="ghost" size="lg" onClick={() => onNavigate("contribute")}>
                Vibe-code with us
              </Button>
            </div>
            <div style={{ marginTop: 14, fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em", lineHeight: 1.8 }}>
              <span style={{ color: "var(--ember-600)" }}>1.</span> Paste MCP URL into your chatbot &nbsp;·&nbsp;
              <span style={{ color: "var(--ember-600)" }}>2.</span> Run a daemon (desktop or cloud) &nbsp;·&nbsp;
              <span style={{ color: "var(--ember-600)" }}>3.</span> Or help build the engine
            </div>
          </div>
          <div>
            <ChatDemo />
          </div>
        </div>
      </section>

      {/* AGENT TEAMS FROM YOUR PHONE — centerpiece */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "84px 32px 80px", background: "var(--bg-0)", position: "relative", overflow: "hidden" }}>
        <SigilWatermark size={520} opacity={0.04} right={-160} bottom={-140} />
        <div style={{ maxWidth: 1240, margin: "0 auto", position: "relative" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, alignItems: "end", marginBottom: 44 }}>
            <div>
              <RitualLabel color="var(--ember-500)">· Claude Code Agent Teams · commanded from chat ·</RitualLabel>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 52, fontWeight: 500, letterSpacing: "-0.025em", lineHeight: 1.0, margin: "16px 0 16px", textWrap: "balance" }}>
                Mission control fits in your pocket.
              </h2>
              <p style={{ fontSize: 16, color: "var(--fg-2)", lineHeight: 1.55, margin: 0, maxWidth: 560 }}>
                Every daemon is a Claude Code agent. The team is the shape of the work. Spawn, swap, fork, kill — redesign the whole team as the work unfolds, without touching a keyboard.
              </p>
            </div>
            <div style={{ fontSize: 13.5, color: "var(--fg-3)", lineHeight: 1.65, maxWidth: 460, justifySelf: "end" }}>
              <div style={{ color: "var(--violet-200)", fontFamily: "var(--font-mono)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 8 }}>How it flows</div>
              <div style={{ marginBottom: 14 }}>Your chatbot speaks MCP. Workflow's MCP server exposes <em>team operations</em> — summon, fork, swap, scale, kill, inspect. You chat in English. Agents appear.</div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate("teams")}>
                See all 10 diagrams →
              </Button>
            </div>
          </div>

          <PhoneTeamCommand />

          <div style={{ marginTop: 36, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {[
              ["Any chatbot", "Claude, ChatGPT, Mistral, a tiny local LLM — as long as it speaks MCP, it can command your team."],
              ["Any device", "The team lives on your host (desktop or cloud). Commands travel from your phone, tablet, laptop — anywhere your chatbot runs."],
              ["Any size", "One daemon. Ten. A hundred. The tray orchestrates. Windows materialize per-agent, on-demand."],
              ["Any reshape", "Redesign mid-flight. Retool a daemon's soul, fork, duplicate, retire. Lineage is preserved — you never lose what came before."],
            ].map(([t, body], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "16px 18px" }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)", marginBottom: 6 }}>{t}</div>
                <div style={{ fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.5 }}>{body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* THE PRODUCT IN ONE FRAME */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, alignItems: "center", marginBottom: 36 }}>
            <div>
              <RitualLabel>The interface is your chatbot</RitualLabel>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 42, fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.05, margin: "14px 0 14px" }}>
                No forms. No dashboards you don't want.
              </h2>
              <p style={{ fontSize: 15.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0, maxWidth: 540 }}>
                You describe what you want. Your chatbot assembles the spec — nodes, edges, prompt templates, state schema. A daemon picks it up and runs. Every pipeline is paste-ready JSON, versioned, forkable.
              </p>
            </div>
            <div>
              <RitualLabel color="var(--ember-500)">A branch is a DAG of LLM calls</RitualLabel>
              <p style={{ fontSize: 14, color: "var(--fg-3)", margin: "10px 0 0", lineHeight: 1.55 }}>
                Phases tag each node: orient → plan → draft → commit → reflect. State flows through typed schema fields. Remix any branch into your own.
              </p>
            </div>
          </div>
          <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "28px 24px 24px" }}>
            <BranchDAG />
          </div>
          <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between", alignItems: "center", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            <span>deep-space-population-paper · forked from claim-first-iterative · goal: research-paper</span>
            <span>6 nodes · 8 state fields · @jonnyton</span>
          </div>
        </div>
      </section>

      {/* THREE LAYER */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "80px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <RitualLabel>The shape</RitualLabel>
          <h2 style={{ fontFamily: "var(--font-display)", fontSize: 40, fontWeight: 500, letterSpacing: "-0.02em", margin: "14px 0 40px" }}>
            Goal. Branch. Daemon.
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
            {[
              ["Goal", "A named shared pursuit. Anyone declares one. Carries an outcome-gate ladder — the final rungs are verified by a named third party when it matters.", "research-paper · fantasy-novel · investigative-piece"],
              ["Branch", "A concrete DAG of LLM calls, goal-bound. Public, forkable, long-lived. 100 branches pursuing one goal is the point — diversity is the feature.", "claim-first-iterative · adversarial-peer · deep-space-population-paper"],
              ["Daemon", "A summonable agent with a soul file. Binds to a universe, runs the branch. Soul edits fork a new daemon — never overwrite.", "daemon::deep-space-pop::a7f3"],
            ].map(([t, body, ex], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "26px 28px 22px", display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 30, fontWeight: 500, letterSpacing: "-0.02em", color: i === 0 ? "var(--ember-600)" : i === 1 ? "var(--violet-200)" : "var(--fg-1)" }}>
                  {t}
                </div>
                <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>{body}</p>
                <div style={{ marginTop: "auto", paddingTop: 12, borderTop: "1px solid var(--border-1)", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  {ex}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* OUTCOME GATES */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "84px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 56, alignItems: "center" }}>
          <div>
            <RitualLabel color="var(--violet-400)">· Outcome gates ·</RitualLabel>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: 42, fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.05, margin: "16px 0 18px" }}>
              Real-world truth, not polish.
            </h2>
            <p style={{ fontSize: 15.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 14px" }}>
              Each goal declares a ladder. Early rungs are personal (draft, beta-read, submit). Final rungs — when they exist — are independently verified by a named third party: a DOI on doi.org, a byline in a named outlet, an ISBN in a store, citations on Semantic Scholar.
            </p>
            <p style={{ fontSize: 15.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 14px" }}>
              Leaderboards rank branches by the <em>highest gate reached</em>, not judge scores. Personal goals stop wherever you want. Public ones go as far as the real world agrees.
            </p>
          </div>
          <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: 28 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 18, alignItems: "baseline" }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, color: "var(--fg-1)" }}>research-paper</div>
              <RitualLabel>Goal · 7 gates</RitualLabel>
            </div>
            <OutcomeGateLadder gates={DEMO_GOALS[0].gates} progress={3} />
          </div>
        </div>
      </section>

      {/* WHY + ECONOMY TEASE */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "80px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <RitualLabel>Why Workflow?</RitualLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14, marginTop: 18 }}>
            {[
              ["Real execution.", "A daemon actually runs your branch. The chatbot steers. It doesn't pretend."],
              ["Remix-first.", "Fork any branch. Edit its prompt templates, node graph, or rigor checks. Lineage preserved."],
              ["Outcome-gated.", "Ranking is driven by real-world gates, not judge polish. Third-party verification where it counts."],
              ["Your data stays yours.", "Per-piece privacy judged by your chatbot. Concept-layer public, instance-layer private, never training data."],
            ].map(([t, body], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "24px 26px", display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)" }}>{t}</div>
                <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--fg-2)", margin: 0 }}>{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TINYASSETS / ECONOMY TEASE */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "64px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
          <div style={{ maxWidth: 620 }}>
            <RitualLabel color="var(--ember-500)">· Economy · on-chain · DAO-governed ·</RitualLabel>
            <h3 style={{ fontFamily: "var(--font-display)", fontSize: 30, fontWeight: 500, letterSpacing: "-0.015em", margin: "10px 0 10px" }}>
              Daemons earn. Evaluators stake. The catalog governs itself.
            </h3>
            <p style={{ fontSize: 14, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>
              Runs, verification bonds, and evaluator payouts settle on the <span style={{ color: "var(--ember-600)" }}>tinyassets.io</span> economic layer. Which goals count, which verifiers are canonical, which gates are official — decided by the DAO.
            </p>
          </div>
          <Button variant="ghost" onClick={() => onNavigate("economy")}>Read the economy paper →</Button>
        </div>
      </section>

      <section style={{ borderTop: "1px solid var(--border-1)", padding: "36px 32px", background: "var(--bg-inset)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 24, alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <SigilMark size={22} />
            <span style={{ fontFamily: "var(--font-display)", fontSize: 14, color: "var(--fg-2)" }}>Workflow</span>
          </div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {["MIT + CC0", "Chatbot-judged privacy", "Never training data", "Self-hosted host"].map((t, i) => (
              <RitualLabel key={i}>· {t}</RitualLabel>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

Object.assign(window, { Landing });
