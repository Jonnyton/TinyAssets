// Connect.jsx — radical simplicity. "Add the connector. Then talk to your chatbot."

function Connect() {
  const [copied, setCopied] = React.useState(false);
  const url = "https://tinyassets.io/mcp";
  const copy = () => {
    navigator.clipboard?.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: "100px 32px 80px" }}>
      <RitualLabel color="var(--violet-400)">· Zero install · two steps ·</RitualLabel>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: 80, fontWeight: 400, letterSpacing: "-0.035em", lineHeight: 0.95, margin: "20px 0 20px", fontVariationSettings: "'opsz' 144, 'SOFT' 50" }}>
        Add the connector. Then talk.
      </h1>
      <p style={{ fontSize: 18, color: "var(--fg-2)", margin: "0 0 52px", lineHeight: 1.5 }}>
        Paste one URL into your chatbot's connector settings. That's it. Your chatbot can now browse goals, fork branches, and summon daemons — just ask it to.
      </p>

      <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: 28, marginBottom: 48 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 14 }}>
          MCP Server URL
        </div>
        <div style={{ display: "flex", gap: 0 }}>
          <input
            readOnly
            value={url}
            style={{
              background: "var(--bg-inset)", color: "var(--fg-1)",
              border: "1px solid var(--border-1)", borderRight: "none",
              borderRadius: "8px 0 0 8px", padding: "16px 18px",
              fontFamily: "var(--font-mono)", fontSize: 15, width: "100%", outline: "none",
            }}
          />
          <button onClick={copy} style={{
            background: copied ? "var(--signal-live)" : "var(--ember-600)",
            color: copied ? "#0e2b1d" : "var(--fg-on-ember)", border: "none",
            padding: "0 28px", borderRadius: "0 8px 8px 0",
            fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 600, cursor: "pointer", minWidth: 130,
            transition: "all 200ms",
          }}>
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        {[
          ["1", "Add it.", "In your chatbot (Claude.ai, etc.), open connector settings and paste the URL. Approve."],
          ["2", "Talk.", "Start a new chat. Say: 'browse research-paper branches' or 'fork fantasy-novel / claim-first.' Your chatbot steers."],
        ].map(([n, t, body]) => (
          <div key={n} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "24px 26px" }}>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 48, fontWeight: 400, color: "var(--ember-600)", lineHeight: 1, fontVariationSettings: "'opsz' 144, 'SOFT' 50", marginBottom: 12 }}>{n}</div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)", marginBottom: 8 }}>{t}</div>
            <p style={{ fontSize: 14, color: "var(--fg-2)", lineHeight: 1.55, margin: 0 }}>{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { Connect });
