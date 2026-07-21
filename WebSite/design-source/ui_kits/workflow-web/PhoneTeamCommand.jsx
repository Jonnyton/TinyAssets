// PhoneTeamCommand.jsx — the centerpiece beat.
// Left: phone-frame with a chat thread commanding an Agent Team
// Right: live visualization of the team being spawned/retooled in response

function PhoneTeamCommand() {
  const [tick, setTick] = React.useState(0);
  // Cycle through team states every ~3.2s to show live redesign
  React.useEffect(() => {
    const id = setInterval(() => setTick(t => (t + 1) % 4), 3200);
    return () => clearInterval(id);
  }, []);

  // Team state at each tick — user redesigns by chatting
  const teamStates = [
    { // tick 0: base team, 3 daemons
      label: "Current team · 3 agents",
      daemons: [
        { id: "a7f3", name: "claim-first",        role: "draft",      color: "var(--ember-600)",  status: "live" },
        { id: "d12e", name: "adversarial-peer",   role: "review",     color: "var(--violet-400)", status: "live" },
        { id: "b891", name: "citation-hunter",    role: "retrieve",   color: "var(--signal-live)", status: "idle" },
      ],
    },
    { // tick 1: user asked for more parallelism
      label: "Scaling up · 5 agents",
      daemons: [
        { id: "a7f3", name: "claim-first",        role: "draft",      color: "var(--ember-600)",  status: "live" },
        { id: "a7f4", name: "claim-first-b",      role: "draft",      color: "var(--ember-500)",  status: "live" },
        { id: "d12e", name: "adversarial-peer",   role: "review",     color: "var(--violet-400)", status: "live" },
        { id: "b891", name: "citation-hunter",    role: "retrieve",   color: "var(--signal-live)", status: "live" },
        { id: "c004", name: "style-polish",       role: "finish",     color: "var(--violet-200)", status: "idle" },
      ],
    },
    { // tick 2: user swapped a daemon
      label: "Retooling · swap in evaluator",
      daemons: [
        { id: "a7f3", name: "claim-first",        role: "draft",      color: "var(--ember-600)",  status: "live" },
        { id: "a7f4", name: "claim-first-b",      role: "draft",      color: "var(--ember-500)",  status: "live" },
        { id: "e519", name: "gate-evaluator",     role: "judge",      color: "var(--signal-idle)", status: "live" },
        { id: "b891", name: "citation-hunter",    role: "retrieve",   color: "var(--signal-live)", status: "live" },
        { id: "c004", name: "style-polish",       role: "finish",     color: "var(--violet-200)", status: "idle" },
      ],
    },
    { // tick 3: user spawned more
      label: "Live · 7 agents running",
      daemons: [
        { id: "a7f3", name: "claim-first",        role: "draft",      color: "var(--ember-600)",  status: "live" },
        { id: "a7f4", name: "claim-first-b",      role: "draft",      color: "var(--ember-500)",  status: "live" },
        { id: "a7f5", name: "claim-first-c",      role: "draft",      color: "var(--ember-500)",  status: "live" },
        { id: "e519", name: "gate-evaluator",     role: "judge",      color: "var(--signal-idle)", status: "live" },
        { id: "e520", name: "gate-evaluator-b",   role: "judge",      color: "var(--signal-idle)", status: "live" },
        { id: "b891", name: "citation-hunter",    role: "retrieve",   color: "var(--signal-live)", status: "live" },
        { id: "c004", name: "style-polish",       role: "finish",     color: "var(--violet-200)", status: "live" },
      ],
    },
  ];

  const current = teamStates[tick];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 36, alignItems: "start" }}>
      {/* PHONE MOCKUP */}
      <PhoneFrame tick={tick} />

      {/* LIVE TEAM VISUALIZATION */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
          <div>
            <RitualLabel color="var(--ember-500)">· Your agent team · live ·</RitualLabel>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 500, letterSpacing: "-0.015em", marginTop: 8 }}>
              {current.label}
            </div>
          </div>
          <StatusPill kind="live" pulse>mcp · tinyassets.io</StatusPill>
        </div>

        <TeamGrid daemons={current.daemons} />

        <div style={{ marginTop: 18, padding: "14px 18px", background: "var(--bg-inset)", border: "1px dashed var(--border-2)", borderRadius: 10, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", lineHeight: 1.7 }}>
          <div><span style={{ color: "var(--ember-600)" }}>$</span> last command: <span style={{ color: "var(--fg-1)" }}>{COMMAND_HISTORY[tick]}</span></div>
          <div>∙ team reshape committed · soul files preserved · lineage intact</div>
        </div>
      </div>
    </div>
  );
}

const COMMAND_HISTORY = [
  "summon claim-first + adversarial-peer + citation-hunter",
  "clone claim-first twice · add style-polish",
  "replace citation-hunter with gate-evaluator",
  "fork all drafters once · duplicate evaluator",
];

/* ---------- Phone frame with chat thread ---------- */
function PhoneFrame({ tick }) {
  const threads = [
    // tick 0
    [
      { role: "you", text: "spin up a team for the deep-space-population paper" },
      { role: "bot", text: "Summoning claim-first, adversarial-peer, and citation-hunter on papers/. 3 daemons live." },
    ],
    // tick 1
    [
      { role: "you", text: "spin up a team for the deep-space-population paper" },
      { role: "bot", text: "Summoning claim-first, adversarial-peer, and citation-hunter on papers/. 3 daemons live." },
      { role: "you", text: "i need more drafters. clone claim-first x2 and add a style polish pass" },
      { role: "bot", text: "Forking claim-first → claim-first-b. Adding style-polish. Team is now 5 agents." },
    ],
    // tick 2
    [
      { role: "you", text: "i need more drafters. clone claim-first x2 and add a style polish pass" },
      { role: "bot", text: "Forking claim-first → claim-first-b. Adding style-polish. Team is now 5 agents." },
      { role: "you", text: "actually swap citation-hunter for a gate-evaluator — i care about the peer-review gate" },
      { role: "bot", text: "Retiring citation-hunter. Spawning gate-evaluator tuned for peer-review. Lineage preserved." },
    ],
    // tick 3
    [
      { role: "you", text: "actually swap citation-hunter for a gate-evaluator — i care about the peer-review gate" },
      { role: "bot", text: "Retiring citation-hunter. Spawning gate-evaluator tuned for peer-review. Lineage preserved." },
      { role: "you", text: "bring citation-hunter back, and duplicate the drafters and evaluator. run 7 in parallel." },
      { role: "bot", text: "Team reshaped: 3 drafters, 2 evaluators, 1 retriever, 1 finisher. All live on papers/." },
    ],
  ];
  const thread = threads[tick];

  return (
    <div style={{ position: "relative" }}>
      {/* Device frame */}
      <div style={{
        width: 300, height: 610, borderRadius: 44,
        background: "linear-gradient(170deg, #1a1a2e 0%, #0e0e1a 100%)",
        padding: 10,
        boxShadow: "0 40px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.06), inset 0 0 0 2px rgba(255,255,255,0.04)",
        position: "relative",
      }}>
        {/* Screen */}
        <div style={{
          width: "100%", height: "100%",
          borderRadius: 36,
          background: "var(--bg-1)",
          overflow: "hidden",
          position: "relative",
          display: "flex", flexDirection: "column",
        }}>
          {/* Notch */}
          <div style={{
            position: "absolute", top: 10, left: "50%", transform: "translateX(-50%)",
            width: 100, height: 26, borderRadius: 14,
            background: "#000", zIndex: 10,
          }} />
          {/* Status bar */}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "14px 26px 0",
            fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-1)", fontWeight: 600,
          }}>
            <span>9:41</span>
            <span style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 9, color: "var(--fg-2)" }}>
              <span>●●●●</span><span>5G</span><span>100%</span>
            </span>
          </div>
          {/* App header */}
          <div style={{
            padding: "28px 16px 10px", display: "flex", alignItems: "center", gap: 10,
            borderBottom: "1px solid var(--border-1)",
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: "radial-gradient(circle, var(--ember-600) 0%, var(--violet-600) 100%)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13,
            }}>✦</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-1)" }}>Claude</div>
              <div style={{ fontSize: 10, color: "var(--signal-live)" }}>● workflow · tinyassets.io/mcp</div>
            </div>
          </div>

          {/* Thread */}
          <div style={{
            flex: 1, overflow: "hidden", padding: "14px 12px",
            display: "flex", flexDirection: "column", gap: 8,
            justifyContent: "flex-end",
          }}>
            {thread.map((m, i) => (
              <div key={`${tick}-${i}`} style={{
                alignSelf: m.role === "you" ? "flex-end" : "flex-start",
                maxWidth: "85%",
                background: m.role === "you" ? "var(--ember-600)" : "var(--bg-2)",
                color: m.role === "you" ? "var(--fg-on-ember)" : "var(--fg-1)",
                border: m.role === "you" ? "none" : "1px solid var(--border-1)",
                borderRadius: m.role === "you" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                padding: "9px 12px",
                fontSize: 12, lineHeight: 1.4,
                animation: i === thread.length - 1 ? "fadeSlide 420ms ease-out" : undefined,
              }}>
                {m.text}
              </div>
            ))}
          </div>

          {/* Compose bar */}
          <div style={{
            padding: "10px 12px 14px",
            borderTop: "1px solid var(--border-1)",
            display: "flex", gap: 8, alignItems: "center",
          }}>
            <div style={{
              flex: 1, background: "var(--bg-inset)", borderRadius: 16,
              padding: "8px 12px", fontSize: 11, color: "var(--fg-3)",
              fontStyle: "italic",
            }}>command your team…</div>
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: "var(--ember-600)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--fg-on-ember)", fontSize: 14,
            }}>↑</div>
          </div>

          {/* Home indicator */}
          <div style={{
            position: "absolute", bottom: 6, left: "50%", transform: "translateX(-50%)",
            width: 100, height: 3, borderRadius: 2,
            background: "rgba(255,255,255,0.3)",
          }} />
        </div>
      </div>

      {/* Tick progress dots */}
      <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 18 }}>
        {[0,1,2,3].map(i => (
          <div key={i} style={{
            width: i === tick ? 20 : 6, height: 4, borderRadius: 2,
            background: i === tick ? "var(--ember-600)" : "var(--border-2)",
            transition: "all 300ms",
          }} />
        ))}
      </div>

      <style>{`
        @keyframes fadeSlide {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

/* ---------- Team grid (right side) ---------- */
function TeamGrid({ daemons }) {
  // Group by role for a clean team view
  const roleOrder = ["draft", "retrieve", "review", "judge", "finish"];
  const roleLabels = {
    draft: "Drafters",
    retrieve: "Retrievers",
    review: "Reviewers",
    judge: "Evaluators",
    finish: "Finishers",
  };
  const byRole = {};
  for (const d of daemons) {
    if (!byRole[d.role]) byRole[d.role] = [];
    byRole[d.role].push(d);
  }

  return (
    <div style={{
      background: "var(--bg-2)", border: "1px solid var(--border-1)",
      borderRadius: 14, padding: "20px 22px", minHeight: 340,
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {roleOrder.map(role => {
          const inRole = byRole[role];
          if (!inRole || inRole.length === 0) return null;
          return (
            <div key={role}>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                textTransform: "uppercase", letterSpacing: "0.14em",
                marginBottom: 8,
              }}>
                {roleLabels[role]} · {inRole.length}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {inRole.map(d => <AgentCard key={d.id} daemon={d} />)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AgentCard({ daemon }) {
  return (
    <div style={{
      background: "var(--bg-inset)",
      border: `1px solid ${daemon.color}55`,
      borderLeft: `3px solid ${daemon.color}`,
      borderRadius: 8,
      padding: "10px 12px",
      minWidth: 180,
      display: "flex", flexDirection: "column", gap: 4,
      animation: "agentAppear 380ms ease-out",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-1)", fontWeight: 600 }}>
          {daemon.name}
        </span>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase",
          color: daemon.status === "live" ? "var(--signal-live)" : "var(--fg-3)",
        }}>
          {daemon.status === "live" ? "● live" : "○ idle"}
        </span>
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", letterSpacing: "0.04em" }}>
        daemon::{daemon.id}
      </div>
      <style>{`
        @keyframes agentAppear {
          from { opacity: 0; transform: scale(0.95) translateY(-4px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>
    </div>
  );
}

Object.assign(window, { PhoneTeamCommand });
