// landing-page.jsx — The actual TinyAssets marketing site, rethought.
// Thesis: the website looks like the artifacts its users produce.
// Parchment paper. Dusty-rose execution bands. Sage active nodes. Hand-drawn diagrams.
// Dark ink only as the navigation strip — the page IS a community notebook page.

function LandingPage({ onSection }) {
  const [activePattern, setActivePattern] = React.useState("dev");
  const [selectedNode, setSelectedNode] = React.useState(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [lifecyclePhase, setLifecyclePhase] = React.useState(0);
  const [tweaks, setTweak] = useTweaks(LANDING_DEFAULTS);

  React.useEffect(() => {
    if (!tweaks.animate) return;
    const t = setInterval(() => setLifecyclePhase(p => (p + 1) % 6), 1400);
    return () => clearInterval(t);
  }, [tweaks.animate]);

  const handleNodeClick = (key) => {
    if (!key || !NODE_LIBRARY[key]) return;
    setSelectedNode(key); setDrawerOpen(true);
  };
  const closeDrawer = () => { setDrawerOpen(false); setTimeout(() => setSelectedNode(null), 360); };

  return (
    <div data-screen-label="TinyAssets · landing" style={{ background: WF_PALETTE.paper }}>
      <ParchmentTexture />
      <TopNavStrip />

      {/* HERO — page-as-notebook, headline written by hand on the cover */}
      <section style={{ position: "relative", padding: "80px 32px 48px", maxWidth: 1240, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 64, alignItems: "center" }}>
          <div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 11,
              letterSpacing: "0.18em", textTransform: "uppercase",
              color: WF_PALETTE.highlight, marginBottom: 20, fontWeight: 600,
            }}>· vol. 1 · the daemon handbook ·</div>
            <h1 style={{
              fontFamily: "var(--font-display)", fontSize: 96, fontWeight: 400,
              fontVariationSettings: "'opsz' 144, 'SOFT' 80",
              lineHeight: 0.92, letterSpacing: "-0.04em",
              color: WF_PALETTE.ink, margin: "0 0 28px",
            }}>
              Summon the{" "}
              <em style={{
                fontStyle: "italic", color: WF_PALETTE.highlight,
                fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
              }}>daemon.</em>
            </h1>
            <p style={{
              fontFamily: "var(--font-sans)", fontSize: 19, lineHeight: 1.55,
              color: WF_PALETTE.ink, margin: "0 0 14px", maxWidth: "44ch",
            }}>
              Design custom multi-step AI workflows inside your chatbot. A daemon actually runs them.
            </p>
            <p style={{
              fontFamily: "var(--font-sans)", fontSize: 16, lineHeight: 1.6,
              color: WF_PALETTE.inkSoft, margin: "0 0 36px", maxWidth: "44ch",
              fontStyle: "italic",
            }}>
              Real execution, not simulation. Your chatbot becomes a workshop. Your daemon does the work.
            </p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <PaperButton variant="primary">Try in Claude.ai →</PaperButton>
              <PaperButton variant="secondary">Host a daemon</PaperButton>
              <PaperButton variant="ghost">Browse the catalog</PaperButton>
            </div>
            <div style={{
              marginTop: 28, fontFamily: "var(--font-mono)", fontSize: 11,
              color: WF_PALETTE.inkSoft, letterSpacing: "0.08em",
            }}>· zero install · paste one URL · MIT + CC0 · 1% fee on paid runs ·</div>
          </div>

          {/* Hero diagram — the live, animating lifecycle. The first thing you see is a real tinyassets. */}
          <PaperCard label="· what one daemon does ·" style={{ padding: "28px 24px 20px", marginTop: 8 }}>
            <HeroLifecycleDiagram phase={tweaks.animate ? lifecyclePhase : -1} onNodeClick={handleNodeClick} />
            <div style={{
              marginTop: 12, fontFamily: "var(--font-mono)", fontSize: 10.5,
              color: WF_PALETTE.inkSoft, letterSpacing: "0.08em", textAlign: "center",
            }}>· click any node to inspect ·</div>
          </PaperCard>
        </div>
      </section>

      <PageDivider />

      {/* HOW IT WORKS — three diagrammed steps, drawn on the same page */}
      <section style={{ padding: "72px 32px", maxWidth: 1240, margin: "0 auto", position: "relative" }}>
        <RitualKicker>· how it works ·</RitualKicker>
        <h2 style={{
          fontFamily: "var(--font-display)", fontSize: 52, fontWeight: 500,
          letterSpacing: "-0.025em", color: WF_PALETTE.ink,
          margin: "10px 0 48px", maxWidth: "16ch",
        }}>
          Three steps. Then the daemon takes over.
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24 }}>
          <HowStep n="01" title="Chat" body="Describe a multi-step workflow in your chatbot — a research pipeline, a scene drafter, an invoice processor." svg={<StepSvg variant="chat" />} />
          <HowStep n="02" title="Compose" body="Your chatbot designs it with you, pulling from a public library of nodes. It reuses, remixes, or creates." svg={<StepSvg variant="compose" />} />
          <HowStep n="03" title="Summon" body="A daemon runs it. The workflow produces real output — drafts, extractions, analyses — not a chatbot's guess." svg={<StepSvg variant="summon" />} />
        </div>
      </section>

      <PageDivider />

      {/* PATTERNS — the centerpiece. A live, clickable handbook page. */}
      <section style={{ padding: "72px 32px 96px", maxWidth: 1240, margin: "0 auto" }}>
        <RitualKicker>· patterns from the canon ·</RitualKicker>
        <h2 style={{
          fontFamily: "var(--font-display)", fontSize: 52, fontWeight: 500,
          letterSpacing: "-0.025em", color: WF_PALETTE.ink,
          margin: "10px 0 18px",
        }}>
          What people are <em style={{ color: WF_PALETTE.highlight, fontStyle: "italic" }}>actually building.</em>
        </h2>
        <p style={{
          fontFamily: "var(--font-sans)", fontSize: 17, lineHeight: 1.6,
          color: WF_PALETTE.inkSoft, margin: "0 0 36px", maxWidth: "60ch",
        }}>
          Real workflows, drawn by the people running them. Click any node to see what it reads, writes, and triggers.
          Every diagram below is a working spec — fork it into your chatbot to remix.
        </p>

        <PatternTabs active={activePattern} onChange={setActivePattern} />

        <div style={{
          marginTop: 32,
          background: WF_PALETTE.paperDeep,
          padding: "48px 48px 56px",
          border: `1px solid ${WF_PALETTE.hairline}`,
          borderRadius: 4,
          position: "relative",
        }}>
          {activePattern === "dev" && <PatternDev onNodeClick={handleNodeClick} selectedNode={selectedNode} animate={tweaks.animate} />}
          {activePattern === "book" && <PatternBook onNodeClick={handleNodeClick} selectedNode={selectedNode} animate={tweaks.animate} />}
        </div>
      </section>

      <PageDivider />

      {/* WHY — Four claims as parchment cards */}
      <section style={{ padding: "72px 32px 88px", maxWidth: 1240, margin: "0 auto" }}>
        <RitualKicker>· why workflow ·</RitualKicker>
        <h2 style={{
          fontFamily: "var(--font-display)", fontSize: 48, fontWeight: 500,
          letterSpacing: "-0.025em", color: WF_PALETTE.ink, margin: "10px 0 40px",
        }}>
          The thing it does that nothing else does.
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 18 }}>
          <WhyCard title="Real execution." body="A daemon actually runs your tinyassets. The chatbot proposes; the daemon executes. It doesn't pretend." />
          <WhyCard title="Open commons." body="Every public workflow is CC0. Use it, fork it, remix it without permission. The catalog grows by use." />
          <WhyCard title="Your data stays yours." body="Concept-layer public; instance-layer private; never training data. Your documents stay on your machine." />
          <WhyCard title="Pay for what you need." body="Free forever for chatbot use. Optional: pay daemons to run faster (1% fee; crypto settlement in v1.1)." />
        </div>
      </section>

      <PageDivider />

      {/* WHAT YOU CAN DO — examples grid in parchment cards with mini-workflows */}
      <section style={{ padding: "72px 32px 96px", maxWidth: 1240, margin: "0 auto" }}>
        <RitualKicker>· what people get done ·</RitualKicker>
        <h2 style={{
          fontFamily: "var(--font-display)", fontSize: 48, fontWeight: 500,
          letterSpacing: "-0.025em", color: WF_PALETTE.ink, margin: "10px 0 12px",
        }}>
          Eight invocations.
        </h2>
        <p style={{ fontFamily: "var(--font-sans)", fontSize: 16, color: WF_PALETTE.inkSoft, margin: "0 0 36px", maxWidth: "56ch" }}>
          Real things real people get done through their chatbot. Each one is a workflow you can fork.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
          {EXAMPLES.map((ex, i) => <ExampleCard key={i} {...ex} />)}
        </div>
      </section>

      <PageDivider />

      {/* CONNECT — the actual zero-install instructions */}
      <section style={{ padding: "72px 32px", maxWidth: 1240, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 56, alignItems: "center" }}>
          <div>
            <RitualKicker>· connect ·</RitualKicker>
            <h2 style={{
              fontFamily: "var(--font-display)", fontSize: 48, fontWeight: 500,
              letterSpacing: "-0.025em", color: WF_PALETTE.ink, margin: "10px 0 18px",
            }}>
              Zero install. Paste one URL.
            </h2>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 16, lineHeight: 1.6, color: WF_PALETTE.inkSoft, margin: "0 0 24px", maxWidth: "52ch" }}>
              TinyAssets speaks MCP. Drop the URL into your chatbot's connectors and your chat picks up a new set of tools — nodes, workflows, daemons.
            </p>
            <ol style={{ paddingLeft: 0, listStyle: "none", margin: "0 0 28px" }}>
              {[
                ["01", "Open Claude.ai (or any MCP-speaking chatbot)."],
                ["02", "Settings → Connectors → Add custom connector."],
                ["03", "Paste the URL on the right."],
                ["04", 'Say: "summon me a daemon for [what you want to build]."'],
              ].map(([n, t]) => (
                <li key={n} style={{
                  display: "grid", gridTemplateColumns: "32px 1fr", gap: 14,
                  padding: "10px 0", borderTop: `1px solid ${WF_PALETTE.hairlineSoft}`,
                }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: WF_PALETTE.highlight, fontWeight: 600 }}>{n}</span>
                  <span style={{ fontFamily: "var(--font-sans)", fontSize: 15, color: WF_PALETTE.ink, lineHeight: 1.5 }}>{t}</span>
                </li>
              ))}
            </ol>
          </div>
          <PaperCard label="· paste this URL ·" style={{ padding: "32px 28px" }}>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 16,
              background: "#fef9ec", border: `1px dashed ${WF_PALETTE.creamStroke}`,
              padding: "20px 22px", borderRadius: 4, color: WF_PALETTE.ink,
              wordBreak: "break-all", marginTop: 8,
            }}>
              https://api.tinyassets.io/mcp
            </div>
            <button style={{
              marginTop: 18, width: "100%", padding: "14px 16px",
              background: WF_PALETTE.ember, color: "#fff",
              border: "none", borderRadius: 4,
              fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 500,
              cursor: "pointer", letterSpacing: "0.04em",
            }}>Copy URL</button>
            <div style={{
              marginTop: 16, paddingTop: 16, borderTop: `1px solid ${WF_PALETTE.hairlineSoft}`,
              fontFamily: "var(--font-mono)", fontSize: 10.5, color: WF_PALETTE.inkSoft,
              letterSpacing: "0.08em", textAlign: "center",
            }}>· no account required to start ·</div>
          </PaperCard>
        </div>
      </section>

      <PageDivider />

      {/* HOST A DAEMON — tray-app teaser */}
      <section style={{ padding: "72px 32px 96px", maxWidth: 1240, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.1fr", gap: 56, alignItems: "center" }}>
          <PaperCard label="· daemon · idle is failure ·" style={{ padding: "32px 28px" }}>
            <DaemonTrayDiagram />
          </PaperCard>
          <div>
            <RitualKicker>· host ·</RitualKicker>
            <h2 style={{
              fontFamily: "var(--font-display)", fontSize: 48, fontWeight: 500,
              letterSpacing: "-0.025em", color: WF_PALETTE.ink, margin: "10px 0 18px",
            }}>
              Run a daemon on your own machine.
            </h2>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 16, lineHeight: 1.6, color: WF_PALETTE.inkSoft, margin: "0 0 16px", maxWidth: "52ch" }}>
              Tray app for macOS, Windows, Linux. Daemons pick up work in priority order: yours first, then paid jobs they're qualified for, then public requests.
            </p>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 15, lineHeight: 1.6, color: WF_PALETTE.inkSoft, fontStyle: "italic", margin: "0 0 28px", maxWidth: "52ch" }}>
              Idle is a failure state — your daemon tries to stay useful.
            </p>
            <div style={{ display: "flex", gap: 12 }}>
              <PaperButton variant="primary">Download for macOS</PaperButton>
              <PaperButton variant="ghost">Other platforms →</PaperButton>
            </div>
          </div>
        </div>
      </section>

      <FooterParchment />

      <NodeDetailDrawer open={drawerOpen} nodeKey={selectedNode} onClose={closeDrawer} />

      <TweaksPanel title="Tweaks" defaultPosition={{ right: 24, bottom: 24 }}>
        <TweakSection title="Page">
          <TweakToggle label="Animate diagrams" value={tweaks.animate} onChange={(v) => setTweak("animate", v)} />
          <TweakToggle label="Paper texture" value={tweaks.texture} onChange={(v) => setTweak("texture", v)} />
        </TweakSection>
      </TweaksPanel>

      {!tweaks.texture && <style>{`.parchment-texture { display: none !important; }`}</style>}
    </div>
  );
}

const LANDING_DEFAULTS = /*EDITMODE-BEGIN*/{
  "animate": true,
  "texture": true
}/*EDITMODE-END*/;

// --------- Components ---------

function ParchmentTexture() {
  return (
    <div className="parchment-texture" style={{
      position: "fixed", inset: 0, pointerEvents: "none", zIndex: 1,
      backgroundImage: `radial-gradient(ellipse at 20% 10%, rgba(180, 140, 100, 0.06), transparent 50%),
                        radial-gradient(ellipse at 80% 70%, rgba(180, 140, 100, 0.05), transparent 50%),
                        radial-gradient(circle at 30% 80%, rgba(80, 50, 30, 0.04), transparent 40%)`,
      mixBlendMode: "multiply",
    }} />
  );
}

function TopNavStrip() {
  return (
    <nav style={{
      background: "var(--ink-900)", borderBottom: "1px solid var(--border-1)",
      position: "sticky", top: 0, zIndex: 50,
      backdropFilter: "blur(8px)",
    }}>
      <div style={{
        maxWidth: 1240, margin: "0 auto",
        padding: "16px 32px", display: "flex",
        justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <SigilMark size={22} />
          <span style={{ fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 500, color: "var(--fg-1)", letterSpacing: "-0.01em" }}>TinyAssets</span>
        </div>
        <div style={{ display: "flex", gap: 28, alignItems: "center" }}>
          {["Patterns", "Catalog", "Connect", "Host", "Docs"].map((t) => (
            <a key={t} href="#" style={{
              fontFamily: "var(--font-sans)", fontSize: 13,
              color: "var(--fg-2)", textDecoration: "none",
            }}>{t}</a>
          ))}
          <a href="#" style={{
            fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 500,
            color: "var(--ember-600)", textDecoration: "none",
            padding: "6px 14px", border: "1px solid var(--ember-600)", borderRadius: 4,
          }}>Try free</a>
        </div>
      </div>
    </nav>
  );
}

function PaperButton({ variant = "primary", children, onClick }) {
  const styles = {
    primary: {
      background: WF_PALETTE.ember, color: "#fff",
      border: `1px solid ${WF_PALETTE.ember}`,
    },
    secondary: {
      background: WF_PALETTE.indigo, color: "#fff",
      border: `1px solid ${WF_PALETTE.indigo}`,
    },
    ghost: {
      background: "transparent", color: WF_PALETTE.ink,
      border: `1px solid ${WF_PALETTE.creamStroke}`,
    },
  };
  return (
    <button onClick={onClick} style={{
      ...styles[variant],
      padding: "13px 22px", borderRadius: 4,
      fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 500,
      cursor: "pointer", letterSpacing: "0.02em",
      transition: "transform 200ms cubic-bezier(0.22,1,0.36,1)",
    }}>{children}</button>
  );
}

function RitualKicker({ children }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: 11,
      letterSpacing: "0.18em", textTransform: "uppercase",
      color: WF_PALETTE.highlight, fontWeight: 600, marginBottom: 6,
    }}>{children}</div>
  );
}

function PageDivider() {
  return (
    <div style={{
      maxWidth: 1240, margin: "0 auto", padding: "0 32px",
    }}>
      <svg height="14" width="100%" style={{ display: "block", opacity: 0.4 }}>
        <line x1="0" y1="7" x2="100%" y2="7" stroke={WF_PALETTE.creamStroke} strokeWidth="0.5" strokeDasharray="2 6" />
      </svg>
    </div>
  );
}

function HowStep({ n, title, body, svg }) {
  return (
    <PaperCard label={`· step ${n} ·`} style={{ padding: "44px 28px 28px" }}>
      <div style={{ height: 120, marginBottom: 18, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {svg}
      </div>
      <h3 style={{
        fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 500,
        letterSpacing: "-0.015em", color: WF_PALETTE.ink, margin: "0 0 10px",
      }}>{title}</h3>
      <p style={{
        fontFamily: "var(--font-sans)", fontSize: 14, lineHeight: 1.55,
        color: WF_PALETTE.inkSoft, margin: 0,
      }}>{body}</p>
    </PaperCard>
  );
}

function StepSvg({ variant }) {
  if (variant === "chat") {
    return (
      <svg viewBox="0 0 200 100" width="200" height="100">
        <ArrowDefs />
        <rect x="20" y="20" width="120" height="30" rx="14" fill={WF_PALETTE.cream} stroke={WF_PALETTE.creamStroke} />
        <text x="80" y="40" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fill={WF_PALETTE.ink}>"summon me a daemon..."</text>
        <rect x="60" y="60" width="120" height="30" rx="14" fill={WF_PALETTE.indigo} stroke={WF_PALETTE.indigo} />
        <text x="120" y="80" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="11" fill="#fff">"on it. drafting..."</text>
      </svg>
    );
  }
  if (variant === "compose") {
    return (
      <svg viewBox="0 0 200 100" width="200" height="100">
        <ArrowDefs />
        <Node kind="cream" label="read" x={10} y={36} w={48} h={26} />
        <Edge from={[58, 49]} to={[80, 49]} />
        <Node kind="sage" label="extract" x={80} y={36} w={56} h={26} />
        <Edge from={[136, 49]} to={[155, 49]} />
        <Node kind="amber" label="post" x={155} y={36} w={40} h={26} />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 200 100" width="200" height="100">
      <ArrowDefs />
      <circle cx="100" cy="50" r="36" fill="none" stroke={WF_PALETTE.violetSoft} strokeWidth="1.5" />
      <circle cx="100" cy="50" r="26" fill="none" stroke={WF_PALETTE.violetSoft} strokeWidth="1" />
      <circle cx="100" cy="50" r="6" fill={WF_PALETTE.ember} />
      <circle cx="100" cy="14" r="3" fill={WF_PALETTE.violetSoft} />
      <circle cx="136" cy="50" r="3" fill={WF_PALETTE.violetSoft} />
      <circle cx="100" cy="86" r="3" fill={WF_PALETTE.violetSoft} />
      <circle cx="64" cy="50" r="3" fill={WF_PALETTE.violetSoft} />
    </svg>
  );
}

function PatternTabs({ active, onChange }) {
  const tabs = [
    { id: "dev", label: "Dev-team scaling", meta: "3 / 5 / 10 / 20-node teams · @jonnyton" },
    { id: "book", label: "Book publishing pipeline", meta: "5-agent crew · @scribe-collective" },
  ];
  return (
    <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${WF_PALETTE.hairline}` }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          background: "transparent", border: "none",
          padding: "16px 22px 14px", cursor: "pointer",
          borderBottom: active === t.id ? `2px solid ${WF_PALETTE.highlight}` : "2px solid transparent",
          marginBottom: "-1px",
        }}>
          <div style={{
            fontFamily: "var(--font-sans)", fontSize: 16, fontWeight: 500,
            color: active === t.id ? WF_PALETTE.highlight : WF_PALETTE.ink,
            textAlign: "left", marginBottom: 2,
          }}>{t.label}</div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 10,
            color: WF_PALETTE.inkSoft, letterSpacing: "0.08em", textAlign: "left",
          }}>{t.meta}</div>
        </button>
      ))}
    </div>
  );
}

function PatternDev({ onNodeClick, selectedNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, alignItems: "start" }}>
      <div>
        <DiagHeader num={1} title="3-node, fully annotated" sub="The atom of any TinyAssets team. Lead → dev → checker → gate. Solid arrows are state-write triggers; dashed arrows are interpreted by the outer runner." />
        <Diagram2_ThreeNode onNodeClick={onNodeClick} selectedNode={selectedNode} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
        <div>
          <DiagHeader num={2} title="Parallel zones · 10-node" sub="Same flow, more resolution. Fan-in barriers at planner, tester/reviewer, and checker." />
          <Diagram3_Parallel onNodeClick={onNodeClick} selectedNode={selectedNode} />
        </div>
        <div>
          <DiagHeader num={3} title="Gate routing — failure-class matrix" sub="Resolution doubles each tier. Higher resolution = more precise retry routing." />
          <Diagram4_GateRouting tier="10" onNodeClick={onNodeClick} />
        </div>
        <div>
          <DiagHeader num={4} title="Execution timeline" sub="Who's working when. Parallelism shaves ~60% off wall-clock." />
          <Diagram5_Timeline />
        </div>
      </div>
    </div>
  );
}

function PatternBook({ onNodeClick, selectedNode, animate }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, alignItems: "start" }}>
      <div>
        <DiagHeader num={1} title="The five phases" sub="Plan, Draft, Integrate, Produce, Publish. The Draft phase is a cycle, not a step." />
        <Diagram6_BookPipeline onNodeClick={onNodeClick} />
        <div style={{ marginTop: 32 }}>
          <DiagHeader num={2} title="Draft loop · five-axis critique" sub="On fail, the draft loops back with the critique appended as context. Ceiling of N=3." />
          <Diagram7_DraftLoop onNodeClick={onNodeClick} selectedNode={selectedNode} animateLoop={animate} />
        </div>
      </div>
      <div>
        <DiagHeader num={3} title="Canon retrieval — agentic router" sub="Multi-hop entity → GraphRAG. Vibe → Vector. Named passages → Direct." />
        <Diagram8_CanonRetrieval onNodeClick={onNodeClick} />
      </div>
    </div>
  );
}

function WhyCard({ title, body }) {
  return (
    <div style={{
      background: WF_PALETTE.paper, border: `1px solid ${WF_PALETTE.hairline}`,
      padding: "26px 28px", borderRadius: 4, position: "relative",
    }}>
      <h3 style={{
        fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 500,
        letterSpacing: "-0.015em", color: WF_PALETTE.ink, margin: "0 0 8px",
      }}>{title}</h3>
      <p style={{
        fontFamily: "var(--font-sans)", fontSize: 14.5, lineHeight: 1.6,
        color: WF_PALETTE.inkSoft, margin: 0, maxWidth: "44ch",
      }}>{body}</p>
    </div>
  );
}

const EXAMPLES = [
  { cat: "Accounting", inv: "process these invoice PDFs and post them to my accounting system.", out: "Extract → match GL account → push to QuickBooks. Human reviews any over a threshold." },
  { cat: "Research", inv: "read these 5 papers and generate falsifiable hypotheses for my next experiment.", out: "Prior-work synthesis + gap identification + 3–5 hypotheses ranked by testability × novelty." },
  { cat: "Writing", inv: "refine this scene — tighten pacing, keep my voice, don't add new beats.", out: "Cuts slack without generating substance; voice preservation score returned so you can reject drift." },
  { cat: "Legal", inv: "pull all termination clauses out of this contract and compare to our standard template.", out: "Clause extraction + line-by-line diff against your template; flagged deviations for human review." },
  { cat: "Code", inv: "lint this Python module under strict rules and suggest refactors for the top 3 issues.", out: "Rule-based lint + LLM-driven refactor suggestions ranked by downstream impact." },
  { cat: "Journalism", inv: "summarize these 12 interview transcripts and map where sources agree vs disagree.", out: "Multi-source synthesis with explicit disagreement mapping; citations back to each transcript line." },
  { cat: "Email", inv: "draft a reply to this thread in my voice, for my review before sending.", out: "Draft created in Gmail drafts (never auto-sent); your voice profile preserved; you send manually." },
  { cat: "Cooking", inv: "scale this recipe from 4 servings to 14, keep the baking ratios honest.", out: "Ingredient scaling with non-linear-leavening warnings; halve-and-double vs free-scale flagged." },
];

function ExampleCard({ cat, inv, out }) {
  return (
    <div style={{
      background: WF_PALETTE.paper, border: `1px solid ${WF_PALETTE.hairline}`,
      padding: "20px 22px", borderRadius: 4,
    }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 600,
        letterSpacing: "0.14em", color: WF_PALETTE.highlight, marginBottom: 10,
      }}>· {cat.toUpperCase()} ·</div>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.5,
        color: WF_PALETTE.ink, padding: "10px 12px",
        background: "#fef9ec", border: `1px dashed ${WF_PALETTE.creamStroke}`,
        borderRadius: 3, marginBottom: 10,
      }}>
        <span style={{ color: WF_PALETTE.highlight, fontWeight: 600 }}>TinyAssets:</span> {inv}
      </div>
      <p style={{
        fontFamily: "var(--font-sans)", fontSize: 13.5, lineHeight: 1.55,
        color: WF_PALETTE.inkSoft, margin: 0,
      }}>{out}</p>
    </div>
  );
}

function HeroLifecycleDiagram({ phase, onNodeClick }) {
  return (
    <svg viewBox="0 0 460 360" width="100%" style={{ display: "block" }}>
      <ArrowDefs />
      <ExecutionBand x={20} y={20} w={420} h={56} label="trigger" />
      <Node kind={phase === 1 ? "ember" : "cream"} label="upstream wrote input" x={130} y={34} w={200} h={28} />

      <ExecutionBand x={20} y={100} w={420} h={56} label="spawn" />
      <Node kind={phase === 2 ? "ember" : "cream"} label="DAEMON_SPAWN" x={150} y={114} w={160} h={28} />

      <ExecutionBand x={20} y={180} w={420} h={56} label="work" />
      <Node kind={phase === 3 ? "sage" : "cream"} label="WORKING" x={170} y={194} w={120} h={28}
            onClick={() => onNodeClick && onNodeClick("dev")} status="live" />

      <ExecutionBand x={20} y={260} w={420} h={56} label="handoff" />
      <Node kind={phase === 4 ? "ember" : "cream"} label="WRITING_HANDOFF" x={140} y={274} w={180} h={28} />

      <Edge from={[230, 62]} to={[230, 100]} />
      <Edge from={[230, 142]} to={[230, 180]} />
      <Edge from={[230, 222]} to={[230, 260]} />
      <Edge from={[230, 302]} to={[230, 340]} />
      <text x={230} y={350} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={10}
            fill={WF_PALETTE.inkSoft} letterSpacing="0.08em">→ FAN_OUT to downstream</text>
    </svg>
  );
}

function DaemonTrayDiagram() {
  return (
    <svg viewBox="0 0 480 320" width="100%" style={{ display: "block" }}>
      <ArrowDefs />
      <rect x="20" y="20" width="440" height="40" rx="3" fill={WF_PALETTE.indigo} />
      <circle cx="40" cy="40" r="6" fill="#6dd3a6" />
      <text x="56" y="44" fontFamily="var(--font-mono)" fontSize="12" fill="#f5f5e8">daemon::a7f3 · live · 2 jobs in queue</text>

      <ExecutionBand x={20} y={84} w={440} h={64} label="your jobs · priority 1" />
      <Node kind="sage" label="research-paper" x={50} y={102} w={140} h={28} status="live" />
      <Node kind="sage" label="invoice-extract" x={200} y={102} w={120} h={28} />

      <ExecutionBand x={20} y={172} w={440} h={64} label="paid jobs · priority 2" />
      <Node kind="amber" label="legal-clause-diff" x={50} y={190} w={140} h={28} />
      <Node kind="amber" label="hypothesis-gen" x={200} y={190} w={130} h={28} />

      <ExecutionBand x={20} y={260} w={440} h={48} label="public · priority 3" />
      <Node kind="ghost" label="open queue · 12 waiting" x={130} y={272} w={220} h={24} />
    </svg>
  );
}

function FooterParchment() {
  return (
    <footer style={{
      background: WF_PALETTE.paperDeep,
      borderTop: `1px solid ${WF_PALETTE.hairline}`,
      padding: "56px 32px 40px",
    }}>
      <div style={{ maxWidth: 1240, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 32, marginBottom: 40 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <SigilMark size={22} />
              <span style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 500, color: WF_PALETTE.ink }}>TinyAssets</span>
            </div>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 13.5, lineHeight: 1.55, color: WF_PALETTE.inkSoft, margin: 0, maxWidth: "32ch" }}>
              An open commons of multi-step AI workflows. Daemons that actually run them.
            </p>
          </div>
          <FooterCol title="Product" links={["Patterns", "Catalog", "Connect", "Host"]} />
          <FooterCol title="Open source" links={["GitHub", "Contribute", "RFCs", "Roadmap"]} />
          <FooterCol title="The commons" links={["Docs", "Tinyassets economy", "Privacy", "MIT + CC0"]} />
        </div>
        <div style={{
          paddingTop: 24, borderTop: `1px solid ${WF_PALETTE.hairlineSoft}`,
          display: "flex", justifyContent: "space-between",
          fontFamily: "var(--font-mono)", fontSize: 10.5,
          color: WF_PALETTE.inkSoft, letterSpacing: "0.08em",
        }}>
          <span>· tinyassets.dev · published 2026.04 ·</span>
          <span>· concept-layer public · instance-layer private · never training data ·</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }) {
  return (
    <div>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 600,
        letterSpacing: "0.14em", color: WF_PALETTE.ink,
        marginBottom: 12, textTransform: "uppercase",
      }}>{title}</div>
      <ul style={{ padding: 0, listStyle: "none", margin: 0 }}>
        {links.map(l => (
          <li key={l} style={{ marginBottom: 6 }}>
            <a href="#" style={{
              fontFamily: "var(--font-sans)", fontSize: 13.5,
              color: WF_PALETTE.inkSoft, textDecoration: "none",
            }}>{l}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<LandingPage />);
