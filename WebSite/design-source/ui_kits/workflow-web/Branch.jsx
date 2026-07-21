// Branch.jsx — a Branch is one user's concrete take on a Goal. Branches bind to Goals.
// Lineage: fork preserves parent pointer so improvements flow between variants.

const DEMO_BRANCHES = {
  "research-paper": [
    { id: "br-a7f", name: "claim-first-iterative", author: "@veritas", parent: null, runs: 412, forks: 14, gate: 4, judgeScore: 0.87, summary: "Start with the sharpest claim, iterate evidence, never let intro drift." },
    { id: "br-b21", name: "lit-review-heavy", author: "@stackedpapers", parent: "br-a7f", runs: 189, forks: 6, gate: 3, judgeScore: 0.72, summary: "Forked from claim-first. Front-loads 40+ citation synthesis before any drafting." },
    { id: "br-c90", name: "replication-focused", author: "@cold-fusion-2", parent: null, runs: 67, forks: 2, gate: 6, judgeScore: 0.91, summary: "Pair each claim to a pre-registered replication protocol. Slower start, strongest gates." },
    { id: "br-d12", name: "adversarial-peer", author: "@redteam", parent: "br-a7f", runs: 142, forks: 9, gate: 2, judgeScore: 0.68, summary: "Runs a hostile peer-review simulation between drafts. Kills weak claims early." },
  ],
};

function BranchRow({ branch, rank, onOpen }) {
  return (
    <div
      onClick={() => onOpen && onOpen(branch)}
      style={{
        display: "grid",
        gridTemplateColumns: "32px 2fr 1fr 140px 120px 70px",
        gap: 16,
        alignItems: "center",
        padding: "14px 20px",
        background: "transparent",
        border: "1px solid var(--border-1)",
        borderTop: rank === 1 ? "1px solid var(--border-1)" : "none",
        cursor: "pointer",
        transition: "background 160ms",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-3)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 500, color: rank <= 3 ? "var(--ember-600)" : "var(--fg-3)", textAlign: "right" }}>
        {rank}
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)" }}>{branch.name}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", marginTop: 3 }}>
          {branch.author} · {branch.parent ? `forked from ${branch.parent}` : "original"}
        </div>
        <div style={{ fontSize: 12, color: "var(--fg-2)", marginTop: 6, lineHeight: 1.45 }}>{branch.summary}</div>
      </div>
      <div>
        <RitualLabel>Highest gate</RitualLabel>
        <div style={{ fontSize: 13, color: "var(--fg-1)", fontWeight: 600, marginTop: 3 }}>Gate {branch.gate + 1}</div>
      </div>
      <div>
        <RitualLabel>Runs · Forks</RitualLabel>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-1)", marginTop: 3 }}>
          {branch.runs} · {branch.forks}
        </div>
      </div>
      <div>
        <RitualLabel>Judge</RitualLabel>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--violet-200)", marginTop: 3 }}>
          {branch.judgeScore.toFixed(2)}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--ember-600)" }}>→</span>
      </div>
    </div>
  );
}

function LineageMini({ branches }) {
  // Tiny tree: roots + children. Just show who forked whom.
  const byId = Object.fromEntries(branches.map((b) => [b.id, b]));
  const roots = branches.filter((b) => !b.parent);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>
      {roots.map((r) => {
        const kids = branches.filter((b) => b.parent === r.id);
        return (
          <div key={r.id}>
            <div style={{ color: "var(--fg-1)" }}>● {r.name} <span style={{ color: "var(--fg-3)" }}>· {r.author}</span></div>
            {kids.map((k, i) => (
              <div key={k.id} style={{ color: "var(--fg-2)", marginLeft: 16, marginTop: 4 }}>
                <span style={{ color: "var(--violet-400)" }}>└─</span> {k.name}{" "}
                <span style={{ color: "var(--fg-3)" }}>· {k.author}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

Object.assign(window, { DEMO_BRANCHES, BranchRow, LineageMini });
