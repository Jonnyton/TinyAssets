// hero-shell.jsx — Top chrome: dark ink nav bar + parchment-page hero.
// The page is structured as a "community handbook" — chrome is dark TinyAssets-brand,
// the body is the parchment notebook of real workflows.

function HeroShell({ activeTinyAssets, onTinyAssetsChange }) {
  return (
    <header style={{
      background: "var(--ink-900)",
      borderBottom: "1px solid var(--border-1)",
      position: "relative", overflow: "hidden",
    }}>
      <SigilWatermark size={520} opacity={0.05} right={-160} bottom={-180} />

      {/* Top nav strip */}
      <nav style={{
        maxWidth: 1240, margin: "0 auto",
        padding: "20px 32px", display: "flex",
        justifyContent: "space-between", alignItems: "center",
        position: "relative",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <SigilMark size={26} />
          <span style={{
            fontFamily: "var(--font-display)", fontSize: 18,
            fontWeight: 500, color: "var(--fg-1)",
            letterSpacing: "-0.01em",
          }}>TinyAssets</span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 10,
            color: "var(--fg-3)", marginLeft: 4,
            textTransform: "uppercase", letterSpacing: "0.14em",
          }}>· patterns from the canon ·</span>
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          {["Connect", "Catalog", "Host", "Patterns"].map((t, i) => (
            <a key={i} href="#" style={{
              fontFamily: "var(--font-sans)", fontSize: 13,
              color: t === "Patterns" ? "var(--ember-600)" : "var(--fg-2)",
              textDecoration: "none",
              borderBottom: t === "Patterns" ? "1px solid var(--ember-600)" : "1px solid transparent",
              paddingBottom: 2,
            }}>{t}</a>
          ))}
        </div>
      </nav>

      {/* Hero */}
      <div style={{
        maxWidth: 1240, margin: "0 auto",
        padding: "60px 32px 72px", position: "relative",
        display: "grid", gridTemplateColumns: "1fr 1fr",
        gap: 48, alignItems: "end",
      }}>
        <div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11,
            letterSpacing: "0.14em", textTransform: "uppercase",
            color: "var(--violet-400)", marginBottom: 18,
          }}>· community handbook · vol. 1 ·</div>
          <h1 style={{
            fontFamily: "var(--font-display)",
            fontSize: 76, fontWeight: 400,
            fontVariationSettings: "'opsz' 144, 'SOFT' 50",
            lineHeight: 0.95, letterSpacing: "-0.035em",
            margin: "0 0 24px", color: "var(--fg-1)",
          }}>
            What the daemon is{" "}
            <em style={{
              fontStyle: "italic",
              fontVariationSettings: "'opsz' 144, 'SOFT' 100, 'WONK' 1",
              color: "var(--ember-600)",
            }}>actually doing.</em>
          </h1>
          <p style={{
            fontFamily: "var(--font-sans)", fontSize: 16,
            lineHeight: 1.6, color: "var(--fg-2)",
            margin: "0 0 24px", maxWidth: "52ch",
          }}>
            Real workflows, drawn by the people running them. Click any node to see what it reads, writes, and triggers. Every pattern here is forkable; every diagram is a working spec.
          </p>
          <div style={{
            display: "flex", gap: 8, fontFamily: "var(--font-mono)",
            fontSize: 11, color: "var(--fg-3)",
          }}>
            <span style={{ color: "var(--ember-600)" }}>·</span>
            <span>9 diagrams · 28 nodes · 2 production patterns · all CC0</span>
          </div>
        </div>

        {/* TinyAssets switcher card — the "table of contents" */}
        <div style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid var(--border-1)",
          borderRadius: 12, padding: 24,
          backdropFilter: "blur(8px)",
        }}>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 10,
            letterSpacing: "0.14em", textTransform: "uppercase",
            color: "var(--fg-3)", marginBottom: 14,
          }}>Pick a workflow</div>
          {[
            { id: "dev",  label: "Dev-team scaling",  meta: "3 / 5 / 10 / 20-node teams · @jonnyton" },
            { id: "book", label: "Book publishing pipeline", meta: "Plan → Draft → Publish · @scribe-collective" },
          ].map(w => (
            <button key={w.id}
                    onClick={() => onTinyAssetsChange(w.id)}
                    style={{
                      display: "block", width: "100%",
                      textAlign: "left", padding: "14px 16px", marginBottom: 8,
                      background: activeTinyAssets === w.id ? "rgba(233,69,96,0.12)" : "transparent",
                      border: `1px solid ${activeTinyAssets === w.id ? "rgba(233,69,96,0.4)" : "var(--border-1)"}`,
                      borderRadius: 6,
                      cursor: "pointer",
                      transition: "all 200ms cubic-bezier(0.22,1,0.36,1)",
                      boxShadow: activeTinyAssets === w.id ? "var(--glow-ember)" : "none",
                    }}>
              <div style={{
                fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 500,
                color: activeTinyAssets === w.id ? "var(--ember-600)" : "var(--fg-1)",
                marginBottom: 3,
              }}>{w.label}</div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 10,
                color: "var(--fg-3)", letterSpacing: "0.08em",
              }}>{w.meta}</div>
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function SigilMark({ size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ display: "block" }}>
      <defs>
        <linearGradient id="sigil-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e94560" />
          <stop offset="100%" stopColor="#533483" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="46" fill="none" stroke="url(#sigil-grad)" strokeWidth="1.4" />
      <circle cx="50" cy="50" r="36" fill="none" stroke="#533483" strokeWidth="0.9" opacity="0.7" />
      <polygon points="50,12 60,42 92,42 66,60 76,90 50,72 24,90 34,60 8,42 40,42"
               fill="none" stroke="#533483" strokeWidth="1" opacity="0.85" />
      <circle cx="50" cy="50" r="4" fill="#e94560" />
      <circle cx="50" cy="6" r="2.5" fill="#533483" />
      <circle cx="94" cy="50" r="2.5" fill="#533483" />
      <circle cx="50" cy="94" r="2.5" fill="#533483" />
      <circle cx="6" cy="50" r="2.5" fill="#533483" />
    </svg>
  );
}

function SigilWatermark({ size = 400, opacity = 0.06, right, bottom, top, left }) {
  return (
    <div style={{
      position: "absolute",
      width: size, height: size,
      right, bottom, top, left,
      opacity, pointerEvents: "none",
    }}>
      <SigilMark size={size} />
    </div>
  );
}

Object.assign(window, { HeroShell, SigilMark, SigilWatermark });
