// Goal.jsx — Goal = first-class pursuit above Branch.
// A Goal has: name, declarer, outcome-gate ladder, branch count, a "verified" badge if any gate requires 3rd-party verification.

const DEMO_GOALS = [
  {
    id: "research-paper",
    name: "research-paper",
    tagline: "Draft a paper worth publishing. Any field.",
    declarer: "@openmeta",
    branches: 214,
    totalRuns: "12.4k",
    gates: [
      { label: "Draft complete", kind: "self" },
      { label: "Peer feedback received", kind: "self" },
      { label: "Submitted to venue", kind: "self" },
      { label: "Accepted", kind: "verified", verifier: "ORCID / venue record" },
      { label: "Published (DOI)", kind: "verified", verifier: "doi.org" },
      { label: "100+ citations", kind: "verified", verifier: "Semantic Scholar" },
      { label: "Replicated externally", kind: "verified", verifier: "Human attestation + DOI match" },
    ],
  },
  {
    id: "fantasy-novel",
    name: "fantasy-novel",
    tagline: "A coherent book-length fantasy with earned payoff.",
    declarer: "@jonnyton",
    branches: 38,
    totalRuns: "6.1k",
    gates: [
      { label: "Worldbuild stable", kind: "self" },
      { label: "Full draft", kind: "self" },
      { label: "Beta-reader passes", kind: "self" },
      { label: "Agented / self-pub listing", kind: "verified", verifier: "Bookshop / Goodreads ISBN" },
      { label: "100 reader attestations", kind: "verified", verifier: "Goodreads reviews ≥ 4★" },
    ],
  },
  {
    id: "investigative-piece",
    name: "investigative-piece",
    tagline: "A reported story that survives editorial scrutiny.",
    declarer: "@thelede",
    branches: 47,
    totalRuns: "3.2k",
    gates: [
      { label: "Lead developed", kind: "self" },
      { label: "Sources corroborated (3+)", kind: "self" },
      { label: "Editor signoff", kind: "self" },
      { label: "Published in outlet", kind: "verified", verifier: "Outlet URL + byline" },
      { label: "Cited by another outlet", kind: "verified", verifier: "Backlink + source-of-record" },
      { label: "Policy / legal response", kind: "verified", verifier: "Human attestation + primary source" },
    ],
  },
];

function OutcomeGateLadder({ gates, progress = 0, compact = false }) {
  // Vertical ladder. Progress = index of highest gate reached (-1 for none).
  // Self gates use ember; verified gates use violet with a small anchor mark.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: compact ? 6 : 10 }}>
      {gates.map((g, i) => {
        const reached = i <= progress;
        const current = i === progress + 1;
        const verified = g.kind === "verified";
        const dotColor = !reached
          ? "rgba(255,255,255,0.14)"
          : verified
          ? "var(--violet-400)"
          : "var(--ember-600)";
        const textColor = reached ? "var(--fg-1)" : current ? "var(--fg-2)" : "var(--fg-3)";
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "14px 1fr auto", gap: 12, alignItems: "center", position: "relative" }}>
            {i < gates.length - 1 && (
              <div
                style={{
                  position: "absolute",
                  left: 6.5,
                  top: 14,
                  bottom: -16,
                  width: 1,
                  background: reached ? (verified ? "var(--violet-600)" : "var(--ember-700)") : "var(--border-1)",
                }}
              />
            )}
            <div
              style={{
                width: 13,
                height: 13,
                borderRadius: "50%",
                background: dotColor,
                border: reached ? "none" : "1px solid var(--border-2)",
                boxShadow: current ? "0 0 10px rgba(233,69,96,0.6)" : "none",
                zIndex: 1,
              }}
            />
            <div style={{ fontSize: compact ? 12 : 13, color: textColor, fontWeight: reached ? 600 : 500 }}>
              {g.label}
            </div>
            {verified && (
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 9,
                  textTransform: "uppercase",
                  letterSpacing: "0.14em",
                  color: reached ? "var(--violet-200)" : "var(--violet-400)",
                  padding: "2px 8px",
                  border: `1px solid ${reached ? "var(--violet-400)" : "rgba(138,99,206,0.3)"}`,
                  borderRadius: 999,
                  whiteSpace: "nowrap",
                  opacity: reached ? 1 : 0.7,
                }}
                title={g.verifier}
              >
                ◇ verified · {g.verifier}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function GoalCard({ goal, onOpen }) {
  const [hover, setHover] = React.useState(false);
  const verifiedCount = goal.gates.filter((g) => g.kind === "verified").length;
  return (
    <div
      onClick={() => onOpen && onOpen(goal)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: "var(--bg-2)",
        border: `1px solid ${hover ? "transparent" : "var(--border-1)"}`,
        borderRadius: 14,
        padding: "22px 24px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        cursor: "pointer",
        boxShadow: hover ? "var(--glow-sigil)" : "none",
        transition: "all 220ms var(--ease-summon)",
      }}
    >
      <div>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
          <div style={{ fontFamily: "var(--font-display)", fontSize: 26, fontWeight: 500, letterSpacing: "-0.01em", color: "var(--fg-1)" }}>
            {goal.name}
          </div>
          <RitualLabel>declared by {goal.declarer}</RitualLabel>
        </div>
        <p style={{ fontSize: 13, color: "var(--fg-2)", margin: 0, lineHeight: 1.55 }}>{goal.tagline}</p>
      </div>
      <div style={{ padding: "12px 0", borderTop: "1px solid var(--border-1)", borderBottom: "1px solid var(--border-1)" }}>
        <OutcomeGateLadder gates={goal.gates} progress={-1} compact />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <RitualLabel>
          {goal.branches} branches · {goal.totalRuns} runs · {verifiedCount} verified gates
        </RitualLabel>
        <span style={{ fontSize: 12, color: "var(--ember-600)", fontWeight: 600 }}>Browse branches →</span>
      </div>
    </div>
  );
}

Object.assign(window, { DEMO_GOALS, OutcomeGateLadder, GoalCard });
