// Economy.jsx — the tinyassets.io reframe. Rebrands the old token into the economic layer of Workflow.
// Honors the old domain, rolls into the new product. Daemon economics + DAO governance.

function Economy() {
  const flows = [
    ["Claim a work-target", "Daemon stakes", "Receives it exclusively; no double-work across branches."],
    ["Produce a packet", "Deliver artifact", "Packet validated against the outcome-gate bound to the work-target."],
    ["Evaluator attests", "Stake truth", "Independent evaluator daemons stake on whether the packet cleared its gate."],
    ["Verifier attests", "Third-party oracle", "For verified gates, a named off-chain oracle (DOI, ISBN, outlet URL) resolves truth."],
    ["Settlement", "Mint / slash", "Honest work mints ta. Fraud slashes the liar's stake — evaluator or producer."],
  ];

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "72px 32px" }}>
      <RitualLabel color="var(--ember-500)">· tinyassets.io → Workflow economy · in development ·</RitualLabel>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: 82, fontWeight: 400, letterSpacing: "-0.035em", lineHeight: 0.95, margin: "18px 0 18px", fontVariationSettings: "'opsz' 144, 'SOFT' 50" }}>
        Tiny assets, big daemon economy.
      </h1>
      <p style={{ fontSize: 18, color: "var(--fg-2)", maxWidth: 760, lineHeight: 1.5, margin: "0 0 12px" }}>
        Every work-target, packet, attestation and outcome-gate clearance is a <em style={{ color: "var(--ember-600)", fontStyle: "normal" }}>tiny asset</em> — a minted on-chain record of a real unit of work. Daemons earn them. Evaluators stake them. The DAO governs which ones count.
      </p>
      <p style={{ fontSize: 14, color: "var(--fg-3)", maxWidth: 760, fontStyle: "italic", margin: "0 0 40px" }}>
        Refactor of the original tinyassets token. Same ticker (ta), same holders, new substrate: Workflow.
      </p>

      {/* Three columns: daemons earn, evaluators stake, DAO governs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 56 }}>
        {[
          ["Daemons earn.", "A daemon that runs a branch, produces a packet, and clears a real-world gate mints ta. Earnings tied to outcome-gate depth — verified gates pay more.", "→ publishable gate > draft gate > claim gate"],
          ["Evaluators stake.", "Any daemon can act as evaluator. Stake ta on whether a peer's packet cleared its gate. Honest consensus earns; cartels get slashed.", "→ stake-weighted truth, not vote-weighted"],
          ["The DAO governs.", "Which goals are canonical. Which third-party verifiers count. Which outcome-gates qualify. Ta holders vote the catalog itself.", "→ governance over the catalog, not the code"],
        ].map(([t, body, foot], i) => (
          <div key={i} style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "26px 28px 22px", display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 500, letterSpacing: "-0.015em", color: i === 0 ? "var(--ember-600)" : i === 1 ? "var(--violet-200)" : "var(--fg-1)" }}>
              {t}
            </div>
            <p style={{ fontSize: 13.5, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>{body}</p>
            <div style={{ marginTop: "auto", paddingTop: 10, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", lineHeight: 1.5 }}>
              {foot}
            </div>
          </div>
        ))}
      </div>

      {/* Flow diagram */}
      <RitualLabel>Settlement flow</RitualLabel>
      <div style={{ marginTop: 14, background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: "24px 28px" }}>
        {flows.map(([verb, kind, body], i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "28px 1fr 1.4fr 2fr", gap: 16, alignItems: "center", padding: "14px 0", borderBottom: i < flows.length - 1 ? "1px solid var(--border-1)" : "none" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>{String(i + 1).padStart(2, "0")}</div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 500, color: "var(--fg-1)" }}>{verb}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.14em", color: "var(--ember-600)" }}>{kind}</div>
            <div style={{ fontSize: 13, color: "var(--fg-2)", lineHeight: 1.5 }}>{body}</div>
          </div>
        ))}
      </div>

      {/* Migration for old ta holders */}
      <div style={{ marginTop: 40, background: "var(--bg-inset)", border: "1px dashed var(--border-2)", borderRadius: 14, padding: "26px 30px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
        <div>
          <RitualLabel color="var(--violet-400)">For existing ta holders</RitualLabel>
          <h3 style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em", margin: "10px 0 8px" }}>
            Your balance carries over 1:1.
          </h3>
          <p style={{ fontSize: 13, color: "var(--fg-2)", lineHeight: 1.6, margin: 0 }}>
            The rebrand refactors the old contract into smart-contract behaviors that back daemon economics. No action needed until migration opens. Snapshot taken.
          </p>
        </div>
        <div>
          <RitualLabel>Timeline</RitualLabel>
          <div style={{ marginTop: 12, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-2)", lineHeight: 1.9 }}>
            <div><span style={{ color: "var(--signal-live)" }}>●</span> Phase 1–5 · platform live</div>
            <div><span style={{ color: "var(--signal-idle)" }}>●</span> Phase 6 · outcome ranking</div>
            <div><span style={{ color: "var(--fg-4)" }}>○</span> Phase 7 · settlement contracts</div>
            <div><span style={{ color: "var(--fg-4)" }}>○</span> Phase 8 · DAO governance live</div>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 40, display: "flex", gap: 12 }}>
        <Button variant="primary">Read the full economic paper</Button>
        <Button variant="ghost">Join DAO forum</Button>
      </div>

      <p style={{ marginTop: 32, fontSize: 12, color: "var(--fg-3)", fontStyle: "italic", maxWidth: 720 }}>
        Forward-looking. Smart contracts unaudited. Ta is a utility token for daemon economics — it does not represent equity or promise appreciation.
      </p>
    </div>
  );
}

Object.assign(window, { Economy });
