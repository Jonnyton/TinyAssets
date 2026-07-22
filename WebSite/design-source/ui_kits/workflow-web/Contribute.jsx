// Contribute.jsx — "Vibe-code with us." Open-source the engine, MIT + CC0.
// Third action path. Pitches: clone, pick a thread, ship a PR.

function Contribute({ onNavigate }) {
  return (
    <div>
      {/* HERO */}
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "80px 32px 56px", overflow: "hidden" }}>
        <SigilWatermark size={580} opacity={0.055} right={-160} bottom={-140} />
        <div style={{ position: "relative", display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 48, alignItems: "center" }}>
          <div>
            <RitualLabel color="var(--violet-400)">· Open-source · MIT + CC0 · legion of builders ·</RitualLabel>
            <h1 style={{
              fontFamily: "var(--font-display)",
              fontVariationSettings: "'opsz' 144, 'SOFT' 50",
              fontSize: 78, fontWeight: 400, lineHeight: 0.98,
              letterSpacing: "-0.035em", margin: "22px 0 20px", textWrap: "balance",
            }}>
              <div>Summon a daemon.</div>
              <div style={{
                fontStyle: "italic",
                fontVariationSettings: "'opsz' 144, 'SOFT' 80",
                color: "var(--ember-600)",
                paddingBottom: 8,
              }}>
                Vibe-code with us.
              </div>
            </h1>
            <p style={{ fontSize: 17, lineHeight: 1.55, color: "var(--fg-2)", margin: "0 0 10px", maxWidth: 580 }}>
              The engine is a living Python monorepo. Clone it. Run your own host. Ship a branch back. Soul files preserve your lineage — your daemon was <em>yours</em>, and the commit remembers.
            </p>
            <p style={{ fontSize: 13.5, color: "var(--fg-3)", margin: "0 0 32px", fontStyle: "italic", maxWidth: 580 }}>
              Platform: MIT. Catalog (goals, gates, prompts): CC0. Fork either.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button variant="primary" size="lg" onClick={() => window.open("https://github.com/Jonnyton/Workflow", "_blank")}>
                <span style={{ marginRight: 6 }}>↗</span> github.com/Jonnyton/Workflow
              </Button>
              <Button variant="ghost" size="lg" onClick={() => window.open("https://github.com/Jonnyton/Workflow/blob/main/PLAN.md", "_blank")}>
                Read PLAN.md
              </Button>
            </div>
          </div>

          {/* Repo card */}
          <RepoCard />
        </div>
      </section>

      {/* QUICK START */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "64px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.1fr", gap: 40, alignItems: "start" }}>
            <div>
              <RitualLabel>Quick start · local dev</RitualLabel>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 36, fontWeight: 500, letterSpacing: "-0.02em", margin: "14px 0 14px" }}>
                Four commands to a live daemon.
              </h2>
              <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0, maxWidth: 480 }}>
                Poetry-managed. LangGraph under the hood. The daemon you run locally is the same code that ships in the desktop host — no hidden server.
              </p>
              <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 10 }}>
                <Hint n="1" body="Clone the monorepo." />
                <Hint n="2" body="Install deps (poetry install, one-shot)." />
                <Hint n="3" body="Bind a sandbox universe (ships as tests/fixtures/papers)." />
                <Hint n="4" body="Summon. Your chatbot — or the CLI — steers from here." />
              </div>
            </div>

            <TerminalCard />
          </div>
        </div>
      </section>

      {/* THREADS TO PICK UP */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 20, flexWrap: "wrap", marginBottom: 28 }}>
            <div>
              <RitualLabel color="var(--ember-500)">· Threads · help-wanted ·</RitualLabel>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 36, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 6px" }}>
                Pick a thread. Ship a branch.
              </h2>
              <p style={{ fontSize: 14, color: "var(--fg-2)", margin: 0, maxWidth: 560 }}>
                These are the active fronts in the monorepo. Each maps to a PLAN.md section. Claim one on GitHub — the maintainer triage loop runs twice a week.
              </p>
            </div>
            <Button variant="ghost" onClick={() => window.open("https://github.com/Jonnyton/Workflow/issues?q=is%3Aissue+is%3Aopen+label%3Ahelp-wanted", "_blank")}>
              All open issues →
            </Button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
            <ThreadCard
              tag="core"
              area="daemon runtime"
              title="Wake-on-work-target scheduler"
              body="Replace the current polling loop with an event-queue subscription. Hot path during multi-daemon runs."
              meta={["python · asyncio", "~300 LOC", "has breadcrumb in PLAN.md §4.2"]}
              accent="var(--ember-600)"
            />
            <ThreadCard
              tag="catalog"
              area="goals + gates"
              title="Outcome-gate attestation adapters"
              body="Three new third-party adapters: Semantic Scholar citations, ISBN registry, DOI resolver. CC0 licensed."
              meta={["python · httpx", "adapter pattern", "good first issue"]}
              accent="var(--violet-400)"
            />
            <ThreadCard
              tag="chatbot"
              area="MCP surface"
              title="Streaming trace subscription tool"
              body="Add an MCP tool that streams daemon-trace events to the chatbot so it can narrate runs in real time, not poll."
              meta={["MCP · SSE", "~150 LOC", "bounty: pairs with @jonnyton"]}
              accent="var(--signal-live)"
            />
            <ThreadCard
              tag="desktop"
              area="host app"
              title="Linux tray icon (AppIndicator)"
              body="macOS + Windows tray ship today. Linux needs AppIndicator integration across GNOME/KDE/Hyprland."
              meta={["python · pystray", "OS-specific", "help-wanted"]}
              accent="var(--signal-idle)"
            />
            <ThreadCard
              tag="economy"
              area="tinyassets.io"
              title="Evaluator bond contract"
              body="Solidity contract: evaluators stake on their calls, slash on reversal. Audited template; needs adaptation."
              meta={["solidity · foundry", "pairs with DAO", "funded"]}
              accent="var(--ember-500)"
            />
            <ThreadCard
              tag="docs"
              area="learning path"
              title="Walkthrough: fork your first branch"
              body="End-to-end guide from 'add connector' to 'ship a novel branch'. Markdown + embedded terminal recordings."
              meta={["markdown · asciinema", "no code", "great onboarding"]}
              accent="var(--fg-2)"
            />
          </div>
        </div>
      </section>

      {/* PHILOSOPHY */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "72px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <RitualLabel>How we build</RitualLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginTop: 20 }}>
            {[
              [
                "Vibe-coded, not speced.",
                "PLAN.md is high-level direction. Specs live as design-notes that get rewritten when the code disagrees. The monorepo is the source of truth.",
              ],
              [
                "Soul files, not tickets.",
                "Every daemon-shaped change carries a soul file: what it optimizes for, what it refuses. You don't inherit a bug — you fork its soul.",
              ],
              [
                "Leaderboards, not PRs.",
                "Branches compete. If your retrieval pipeline beats the reference on outcome-gates, your branch becomes the new default — your PR didn't need to merge anything.",
              ],
            ].map(([t, body], i) => (
              <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "24px 26px" }}>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)", marginBottom: 10 }}>{t}</div>
                <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA BAR */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "48px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 500, letterSpacing: "-0.015em", color: "var(--fg-1)", marginBottom: 6 }}>
              Three ways in.
            </div>
            <div style={{ fontSize: 14, color: "var(--fg-3)" }}>
              Use it · run it · build it. Pick any. Some do all three.
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Button variant="ghost" onClick={() => onNavigate("connect")}>① Add connector</Button>
            <Button variant="secondary" onClick={() => onNavigate("host")}>② Summon daemon</Button>
            <Button variant="primary" onClick={() => window.open("https://github.com/Jonnyton/Workflow", "_blank")}>
              ③ Vibe-code with us ↗
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

/* ---------- Repo card (mimics a GitHub repo tile) ---------- */
function RepoCard() {
  return (
    <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, overflow: "hidden" }}>
      <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid var(--border-1)", background: "var(--bg-inset)" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--fg-3)" }}>↗</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 13.5, color: "var(--fg-1)" }}>
            <span style={{ color: "var(--fg-3)" }}>github.com /</span> Jonnyton <span style={{ color: "var(--fg-3)" }}>/</span> <span style={{ color: "var(--ember-600)" }}>Workflow</span>
          </span>
        </div>
        <div style={{ fontSize: 12.5, color: "var(--fg-2)", marginTop: 8, lineHeight: 1.5 }}>
          A global goals engine. Self-hostable. Open-source (MIT platform / CC0 catalog).
        </div>
      </div>
      <div style={{ padding: "14px 20px", display: "flex", gap: 16, flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)" }}>
        <RepoStat icon="★" label="stars" value="2.1k" />
        <RepoStat icon="⑂" label="forks" value="184" />
        <RepoStat icon="◐" label="issues" value="47 open" />
        <RepoStat icon="●" label="languages" value="Python 78% · TS 14% · Rust 6%" color="var(--ember-600)" />
      </div>
      <div style={{ padding: "0 20px 18px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em", margin: "6px 0 8px" }}>Recent commits</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)", lineHeight: 1.8 }}>
          <div><span style={{ color: "var(--signal-live)" }}>a7f3c2d</span> <span style={{ color: "var(--fg-3)" }}>jonnyton</span> · refactor(plan): align docs with full-platform architecture</div>
          <div><span style={{ color: "var(--signal-live)" }}>d12eab8</span> <span style={{ color: "var(--fg-3)" }}>contributor</span> · feat(catalog): semantic-scholar gate adapter</div>
          <div><span style={{ color: "var(--signal-live)" }}>f04a91e</span> <span style={{ color: "var(--fg-3)" }}>jonnyton</span> · fix(daemon): wake-on-work-target race condition</div>
          <div><span style={{ color: "var(--signal-live)" }}>b339ec1</span> <span style={{ color: "var(--fg-3)" }}>contributor</span> · docs: walkthrough for first-branch fork</div>
        </div>
      </div>
    </div>
  );
}

function RepoStat({ icon, label, value, color }) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
      <span style={{ color: color || "var(--fg-3)" }}>{icon}</span>
      <span style={{ color: "var(--fg-1)" }}>{value}</span>
      <span style={{ color: "var(--fg-3)", textTransform: "uppercase", fontSize: 10, letterSpacing: "0.12em" }}>{label}</span>
    </div>
  );
}

/* ---------- Terminal card ---------- */
function TerminalCard() {
  return (
    <div style={{ background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 12, overflow: "hidden" }}>
      <div style={{ display: "flex", gap: 6, padding: "10px 14px", borderBottom: "1px solid var(--border-1)", background: "var(--bg-2)" }}>
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#ff5f57" }} />
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#febc2e" }} />
        <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#28c840" }} />
        <div style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>zsh — ~/src</div>
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.8, padding: "18px 20px" }}>
        <div><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>git clone https://github.com/Jonnyton/Workflow</span></div>
        <div style={{ color: "var(--fg-3)" }}>  Cloning into 'Workflow'... 4271 objects, done.</div>
        <div style={{ marginTop: 6 }}><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>cd Workflow && poetry install</span></div>
        <div style={{ color: "var(--fg-3)" }}>  Resolving dependencies... 142 packages installed.</div>
        <div style={{ marginTop: 6 }}><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>poetry run workflow bind ./tests/fixtures/papers</span></div>
        <div style={{ color: "var(--fg-3)" }}>  ∙ bound universe: papers/ · 3 branches</div>
        <div style={{ marginTop: 6 }}><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>poetry run workflow summon claim-first-iterative</span></div>
        <div style={{ color: "var(--signal-live)" }}>  ● daemon::claim-first::local · live</div>
        <div style={{ color: "var(--fg-3)" }}>  ∙ dashboard: localhost:7349 · tray ready</div>
        <div style={{ color: "var(--fg-3)" }}>  ∙ hot-reload watching fantasy_daemon/, workflow/</div>
        <div style={{ marginTop: 10 }}><span style={{ color: "var(--violet-200)" }}>$ edit → save → daemon restarts with new soul</span></div>
      </div>
    </div>
  );
}

function Hint({ n, body }) {
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "baseline" }}>
      <span style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 400, color: "var(--ember-600)", fontVariationSettings: "'opsz' 144, 'SOFT' 50", lineHeight: 1, minWidth: 28 }}>{n}</span>
      <span style={{ fontSize: 14, color: "var(--fg-2)", lineHeight: 1.55 }}>{body}</span>
    </div>
  );
}

/* ---------- Thread card ---------- */
function ThreadCard({ tag, area, title, body, meta, accent }) {
  return (
    <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "22px 24px", display: "flex", flexDirection: "column", gap: 12, position: "relative" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: accent, textTransform: "uppercase", letterSpacing: "0.14em", fontWeight: 600 }}>
          [{tag}]
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
          {area}
        </span>
      </div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 19, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)", lineHeight: 1.2 }}>
        {title}
      </div>
      <p style={{ fontSize: 13, color: "var(--fg-2)", lineHeight: 1.55, margin: 0 }}>{body}</p>
      <div style={{ marginTop: "auto", paddingTop: 12, borderTop: "1px solid var(--border-1)", display: "flex", flexWrap: "wrap", gap: 6 }}>
        {meta.map((m, i) => (
          <span key={i} style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.1em", background: "var(--bg-inset)", padding: "3px 7px", borderRadius: 3 }}>
            {m}
          </span>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { Contribute });
