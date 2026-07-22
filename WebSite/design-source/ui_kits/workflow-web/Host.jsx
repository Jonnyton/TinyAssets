// Host.jsx — The "Summon a daemon" destination.
// Two paths: download for desktop (local-first) or host in the cloud.
// Scroll down past the fork for a live dashboard preview.

function Host() {
  const [mode, setMode] = React.useState("desktop"); // desktop | cloud
  const [os, setOs] = React.useState("macos");       // macos | windows | linux
  const [selectedUniverse, setSelectedUniverse] = React.useState("papers");

  return (
    <div>
      {/* HERO + FORK */}
      <section style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "80px 32px 40px", overflow: "hidden" }}>
        <SigilWatermark size={560} opacity={0.05} right={-180} bottom={-120} />
        <div style={{ position: "relative", maxWidth: 780 }}>
          <RitualLabel color="var(--violet-400)">· Summon a daemon · pick your host ·</RitualLabel>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: 72, fontWeight: 400, letterSpacing: "-0.035em", lineHeight: 0.98, margin: "20px 0 18px", fontVariationSettings: "'opsz' 144, 'SOFT' 50", textWrap: "balance" }}>
            Run it on your machine,{" "}
            <em style={{ fontStyle: "italic", fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1", color: "var(--ember-600)" }}>
              or in the cloud.
            </em>
          </h1>
          <p style={{ fontSize: 17, color: "var(--fg-2)", lineHeight: 1.55, margin: 0, maxWidth: 640 }}>
            A daemon is a summonable agent with a soul file. It binds to a universe, reads the branch DAG, and runs. You choose where it lives.
          </p>
        </div>

        {/* Mode fork */}
        <div style={{ position: "relative", marginTop: 44, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <ModeCard
            active={mode === "desktop"}
            onClick={() => setMode("desktop")}
            label="Local-first"
            title="Download the desktop host"
            body="One tray icon. Many daemons. All data on your machine. MIT-licensed. No account required. Faster iteration — your files, your FS, your LLM keys."
            meta={["~42 MB", "tray + per-daemon windows", "macOS · Windows · Linux", "MIT"]}
            accent="var(--ember-600)"
          />
          <ModeCard
            active={mode === "cloud"}
            onClick={() => setMode("cloud")}
            label="Hosted"
            title="Host a daemon in the cloud"
            body="Zero install. We run the daemon. Bring your own LLM keys or use ours. Good for always-on branches — a peer-review daemon watching for preprints at 3am doesn't need your laptop open."
            meta={["~30 sec setup", "browser dashboard", "egress-gated, privacy-scoped", "metered"]}
            accent="var(--violet-400)"
          />
        </div>
      </section>

      {/* DOWNLOAD / LAUNCH PANEL */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "52px 32px", background: "var(--bg-0)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          {mode === "desktop" ? (
            <DesktopDownload os={os} setOs={setOs} />
          ) : (
            <CloudLaunch />
          )}
        </div>
      </section>

      {/* DASHBOARD PREVIEW */}
      <section style={{ borderTop: "1px solid var(--border-1)", padding: "60px 32px" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
            <div>
              <RitualLabel>Preview · what you'll see</RitualLabel>
              <h2 style={{ fontFamily: "var(--font-display)", fontSize: 38, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 6px" }}>
                One tray, one window per live daemon.
              </h2>
              <p style={{ fontSize: 14.5, color: "var(--fg-2)", margin: 0, maxWidth: 560, lineHeight: 1.55 }}>
                Branches, daemons, work targets, traces — all local. The dashboard below is identical in desktop and cloud modes.
              </p>
            </div>
            <StatusPill kind="live" pulse>2 daemons live</StatusPill>
          </div>
          <HostDashboard
            selectedUniverse={selectedUniverse}
            setSelectedUniverse={setSelectedUniverse}
          />
        </div>
      </section>
    </div>
  );
}

/* ---------- Mode fork card ---------- */
function ModeCard({ active, onClick, label, title, body, meta, accent }) {
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: "left",
        background: active ? "var(--bg-2)" : "var(--bg-1)",
        border: `1px solid ${active ? accent : "var(--border-1)"}`,
        borderRadius: 14,
        padding: "26px 28px 22px",
        cursor: "pointer",
        position: "relative",
        transition: "all 180ms",
        color: "var(--fg-1)",
        boxShadow: active ? `0 0 0 3px ${accent}22` : "none",
      }}
    >
      <RitualLabel color={accent}>· {label} ·</RitualLabel>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 500, letterSpacing: "-0.015em", marginTop: 10, marginBottom: 10, color: "var(--fg-1)" }}>
        {title}
      </div>
      <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 18px" }}>{body}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, paddingTop: 14, borderTop: "1px solid var(--border-1)" }}>
        {meta.map((m, i) => (
          <span key={i} style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em", background: "var(--bg-inset)", padding: "4px 8px", borderRadius: 4 }}>
            {m}
          </span>
        ))}
      </div>
      {active && (
        <div style={{ position: "absolute", top: 14, right: 14, fontFamily: "var(--font-mono)", fontSize: 10, color: accent, textTransform: "uppercase", letterSpacing: "0.14em" }}>
          ● Selected
        </div>
      )}
    </button>
  );
}

/* ---------- Desktop download ---------- */
function DesktopDownload({ os, setOs }) {
  const builds = {
    macos:   { file: "Workflow-0.4.2-arm64.dmg",       size: "42.1 MB", cmd: "brew install workflow-host" },
    windows: { file: "Workflow-Host-0.4.2-Setup.exe", size: "38.7 MB", cmd: "winget install Jonnyton.WorkflowHost" },
    linux:   { file: "workflow-host_0.4.2_amd64.deb",  size: "36.4 MB", cmd: "curl -sSL get.workflow.host | sh" },
  };
  const b = builds[os];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, alignItems: "start" }}>
      <div>
        <RitualLabel color="var(--ember-500)">· Download · v0.4.2 ·</RitualLabel>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 14px" }}>
          Summon it on your desktop.
        </h3>
        <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 22px" }}>
          Built with Electron + Python. Launches a tray icon. Click a universe folder to bind it — the daemon spins up in a separate window.
        </p>

        {/* OS tabs */}
        <div style={{ display: "flex", gap: 4, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: 4, width: "fit-content", marginBottom: 16 }}>
          {[["macos", "macOS"], ["windows", "Windows"], ["linux", "Linux"]].map(([k, v]) => (
            <button key={k} onClick={() => setOs(k)} style={{
              background: os === k ? "var(--bg-2)" : "transparent",
              border: os === k ? "1px solid var(--border-2)" : "1px solid transparent",
              color: os === k ? "var(--fg-1)" : "var(--fg-3)",
              borderRadius: 7, padding: "8px 16px", fontSize: 13, fontFamily: "var(--font-sans)", fontWeight: 500, cursor: "pointer",
            }}>{v}</button>
          ))}
        </div>

        {/* Primary download */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
          <Button variant="primary" size="lg">
            Download for {os === "macos" ? "macOS" : os === "windows" ? "Windows" : "Linux"} <span style={{ fontFamily: "var(--font-mono)", opacity: 0.8 }}>↓</span>
          </Button>
          <Button variant="ghost" size="lg" onClick={() => window.open("https://github.com/Jonnyton/Workflow/releases", "_blank")}>
            All releases
          </Button>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", lineHeight: 1.8 }}>
          <div>{b.file} · {b.size} · SHA256 verified</div>
          <div>Or: <span style={{ color: "var(--fg-2)" }}>{b.cmd}</span></div>
        </div>
      </div>

      {/* Terminal / quickstart */}
      <div style={{ background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ display: "flex", gap: 6, padding: "10px 14px", borderBottom: "1px solid var(--border-1)", background: "var(--bg-2)" }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#ff5f57" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#febc2e" }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#28c840" }} />
          <div style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>workflow — first run</div>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.75, padding: "18px 20px" }}>
          <div><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>workflow bind ~/papers</span></div>
          <div style={{ color: "var(--fg-3)" }}>  ∙ bound universe: papers/</div>
          <div style={{ color: "var(--fg-3)" }}>  ∙ found 3 branches · no daemons live</div>
          <div style={{ marginTop: 8 }}><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--fg-1)" }}>workflow summon claim-first-iterative</span></div>
          <div style={{ color: "var(--signal-live)" }}>  ● daemon::claim-first::a7f3 · live</div>
          <div style={{ color: "var(--fg-3)" }}>  ∙ tray icon ready · dashboard: localhost:7349</div>
          <div style={{ marginTop: 8 }}><span style={{ color: "var(--fg-3)" }}>$</span> <span style={{ color: "var(--violet-200)" }}>open your chatbot →</span> <em style={{ color: "var(--fg-3)" }}>say:</em></div>
          <div style={{ color: "var(--ember-600)", paddingLeft: 14 }}>  "what's the daemon doing?"</div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Cloud launch ---------- */
function CloudLaunch() {
  const [keyType, setKeyType] = React.useState("byok");
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, alignItems: "start" }}>
      <div>
        <RitualLabel color="var(--violet-400)">· Hosted · no install ·</RitualLabel>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", margin: "12px 0 14px" }}>
          Let us run it for you.
        </h3>
        <p style={{ fontSize: 14.5, color: "var(--fg-2)", lineHeight: 1.6, margin: "0 0 20px" }}>
          Sandboxed VMs with egress-gated FS access. Your universe is a private workspace; only your branches can read it. Same dashboard, accessed via browser.
        </p>
        <div style={{ marginBottom: 18 }}>
          <RitualLabel>Who pays the LLM?</RitualLabel>
          <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
            <ToggleOpt on={keyType === "byok"} onClick={() => setKeyType("byok")} label="Bring your own keys" note="No markup. Anthropic / OpenAI / etc." />
            <ToggleOpt on={keyType === "metered"} onClick={() => setKeyType("metered")} label="Metered by us" note="Pay-as-you-go via tinyassets.io" />
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Button variant="primary" size="lg">
            Launch hosted daemon <span style={{ fontFamily: "var(--font-mono)", opacity: 0.8 }}>→</span>
          </Button>
          <Button variant="ghost" size="lg">See pricing</Button>
        </div>
      </div>

      {/* Launch preview */}
      <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: 22 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em" }}>Launch config</div>
          <StatusPill kind="idle">draft</StatusPill>
        </div>
        <LaunchRow k="Universe" v="papers-public/" />
        <LaunchRow k="Branch" v="claim-first-iterative" />
        <LaunchRow k="Region" v="us-east (iad)" />
        <LaunchRow k="LLM keys" v={keyType === "byok" ? "BYO — anthropic:* · openai:*" : "Metered · $0.00 owed"} />
        <LaunchRow k="Egress scope" v="doi.org · arxiv.org · crossref" />
        <LaunchRow k="Runtime" v="on-demand (wake on work-target)" />
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border-1)", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", lineHeight: 1.7 }}>
          <div>Cold start ≈ 8s · idle ≈ $0 · warm loop billed by runtime-second.</div>
        </div>
      </div>
    </div>
  );
}

function ToggleOpt({ on, onClick, label, note }) {
  return (
    <button onClick={onClick} style={{
      textAlign: "left", flex: 1, minWidth: 200,
      background: on ? "var(--bg-2)" : "var(--bg-inset)",
      border: `1px solid ${on ? "var(--violet-400)" : "var(--border-1)"}`,
      borderRadius: 10, padding: "12px 14px", cursor: "pointer",
      color: "var(--fg-1)",
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)" }}>{label}</div>
      <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 4 }}>{note}</div>
    </button>
  );
}

function LaunchRow({ k, v }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "8px 0", borderBottom: "1px dashed var(--border-1)" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>{k}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--fg-1)" }}>{v}</span>
    </div>
  );
}

/* ---------- Dashboard preview (extracted) ---------- */
function HostDashboard({ selectedUniverse, setSelectedUniverse }) {
  const universes = [
    { id: "papers", name: "papers/", branches: 3, activeDaemons: 2, queue: 7 },
    { id: "the-ashveil", name: "the-ashveil/", branches: 1, activeDaemons: 1, queue: 2 },
    { id: "self-only", name: "invoices/", branches: 1, activeDaemons: 0, queue: 0 },
  ];
  const traces = [
    { t: "00:12:41", kind: "info", msg: "daemon::claim-first-iterative picked work target: draft §3.2" },
    { t: "00:12:44", kind: "info", msg: "retrieval.hybrid → 11 results · vector (6) + kg (3) + notes (2)" },
    { t: "00:12:58", kind: "ok",   msg: "draft committed · packet validated · gate: Draft complete" },
    { t: "00:13:02", kind: "info", msg: "evaluator dispatched · independent reader (haiku)" },
    { t: "00:13:47", kind: "warn", msg: "evaluator flagged: claim on line 84 unsupported · note written" },
    { t: "00:13:48", kind: "info", msg: "work-target registry updated · 'repair §3.2 claim' queued" },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20 }}>
      <div>
        <RitualLabel>Universes on this host</RitualLabel>
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
          {universes.map((u) => {
            const active = u.id === selectedUniverse;
            return (
              <button key={u.id} onClick={() => setSelectedUniverse(u.id)} style={{
                textAlign: "left",
                background: active ? "var(--bg-3)" : "var(--bg-2)",
                border: `1px solid ${active ? "rgba(138,99,206,0.3)" : "var(--border-1)"}`,
                borderRadius: 10, padding: "12px 14px", cursor: "pointer", color: "var(--fg-1)",
              }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--fg-1)", fontWeight: 600 }}>{u.name}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.12em" }}>
                  {u.branches} br · {u.activeDaemons} live · {u.queue} queued
                </div>
              </button>
            );
          })}
          <button style={{ background: "transparent", border: "1px dashed var(--border-2)", borderRadius: 10, padding: "10px 14px", color: "var(--fg-3)", cursor: "pointer", fontSize: 12, fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            + Bind a new universe
          </button>
        </div>
      </div>

      <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderBottom: "1px solid var(--border-1)", background: "var(--bg-inset)" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <div style={{ display: "flex", gap: 6 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--signal-live)", boxShadow: "0 0 6px var(--signal-live)" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "rgba(255,255,255,0.12)" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "rgba(255,255,255,0.12)" }} />
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-2)" }}>papers/ · dashboard</div>
          </div>
          <StatusPill kind="live" pulse>2 daemons live</StatusPill>
        </div>

        <div style={{ padding: 20 }}>
          <RitualLabel>Live daemons</RitualLabel>
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            <DaemonTile name="claim-first-iterative" id="daemon::claim-first::a7f3" meta="branch: claim-first · bound to papers/" status="live" earnings="—" />
            <DaemonTile name="adversarial-peer" id="daemon::adv-peer::d12e" meta="branch: adversarial-peer · bound to papers/" status="live" earnings="—" />
          </div>

          <div style={{ marginTop: 24 }}>
            <RitualLabel>Work-target queue</RitualLabel>
            <div style={{ marginTop: 10, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "10px 14px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-2)", lineHeight: 1.8 }}>
              <div>› <span style={{ color: "var(--ember-600)" }}>draft §3.2</span>            role=publishable · next</div>
              <div>› repair §3.2 claim        role=publishable · blocked by evaluator note</div>
              <div>› worldbuild: ashveil arc  role=notes · low priority</div>
              <div>› synthesize upload: poulton-2024.pdf  role=foundation · hard-block</div>
            </div>
          </div>

          <div style={{ marginTop: 24 }}>
            <RitualLabel>Trace · last 5 minutes</RitualLabel>
            <div style={{ marginTop: 10, background: "var(--bg-inset)", border: "1px solid var(--border-1)", borderRadius: 10, padding: "12px 14px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)", lineHeight: 1.7 }}>
              {traces.map((t, i) => {
                const col = t.kind === "ok" ? "var(--signal-live)" : t.kind === "warn" ? "var(--signal-idle)" : "var(--fg-3)";
                return (
                  <div key={i}>
                    <span style={{ color: "var(--fg-3)" }}>{t.t}</span>{" "}
                    <span style={{ color: col, textTransform: "uppercase", letterSpacing: "0.12em", fontSize: 9 }}>[{t.kind}]</span>{" "}
                    <span>{t.msg}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Host });
