// Catalog.jsx — Goals top-level; drill into a Goal to see its Branches leaderboard.
// Medium density: goal cards above, branch rows below (not grid, not dense table).

function Catalog() {
  const [openGoalId, setOpenGoalId] = React.useState(null);
  const [sort, setSort] = React.useState("gate");

  if (openGoalId) {
    const goal = DEMO_GOALS.find((g) => g.id === openGoalId);
    const branches = (DEMO_BRANCHES[openGoalId] || []).slice().sort((a, b) => {
      if (sort === "gate") return b.gate - a.gate;
      if (sort === "runs") return b.runs - a.runs;
      if (sort === "judge") return b.judgeScore - a.judgeScore;
      return b.forks - a.forks;
    });

    return (
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "56px 32px" }}>
        <button onClick={() => setOpenGoalId(null)} style={{ background: "none", border: "none", color: "var(--fg-2)", fontFamily: "var(--font-mono)", fontSize: 12, cursor: "pointer", padding: 0, textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 24 }}>
          ← All goals
        </button>

        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 40, marginBottom: 36, alignItems: "start" }}>
          <div>
            <RitualLabel color="var(--violet-400)">Goal · declared by {goal.declarer}</RitualLabel>
            <h1 style={{ fontFamily: "var(--font-display)", fontSize: 64, fontWeight: 400, letterSpacing: "-0.03em", margin: "14px 0 14px", fontVariationSettings: "'opsz' 144, 'SOFT' 50" }}>
              {goal.name}
            </h1>
            <p style={{ fontSize: 17, color: "var(--fg-2)", lineHeight: 1.5, maxWidth: 620, margin: "0 0 28px" }}>{goal.tagline}</p>
            <div style={{ display: "flex", gap: 10 }}>
              <Button variant="primary">Fork a branch</Button>
              <Button variant="ghost">Invent a new branch</Button>
            </div>
          </div>
          <div style={{ background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 14, padding: 22 }}>
            <RitualLabel>Outcome-gate ladder</RitualLabel>
            <div style={{ marginTop: 14 }}>
              <OutcomeGateLadder gates={goal.gates} progress={-1} compact />
            </div>
          </div>
        </div>

        <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 14, borderBottom: "1px solid var(--border-1)", paddingBottom: 12 }}>
          <RitualLabel>Branches · {branches.length}</RitualLabel>
          <div style={{ marginLeft: "auto", display: "flex", gap: 4, alignItems: "center" }}>
            <RitualLabel style={{ marginRight: 6 }}>Sort</RitualLabel>
            {[["gate", "Highest gate"], ["runs", "Runs"], ["judge", "Judge"], ["forks", "Forks"]].map(([k, l]) => {
              const active = sort === k;
              return (
                <button key={k} onClick={() => setSort(k)} style={{ background: "transparent", border: "none", fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: 500, color: active ? "var(--ember-600)" : "var(--fg-2)", cursor: "pointer", padding: "4px 8px", position: "relative" }}>
                  {l}
                  {active && <span style={{ position: "absolute", left: 8, right: 8, bottom: 0, height: 1, background: "var(--ember-600)" }} />}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          {branches.map((b, i) => <BranchRow key={b.id} branch={b} rank={i + 1} />)}
        </div>

        <div style={{ marginTop: 40, background: "var(--bg-2)", border: "1px solid var(--border-1)", borderRadius: 12, padding: "22px 24px" }}>
          <RitualLabel>Lineage</RitualLabel>
          <div style={{ marginTop: 14 }}>
            <LineageMini branches={branches} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "60px 32px" }}>
      <RitualLabel color="var(--violet-400)">· Public catalog · CC0 content ·</RitualLabel>
      <h1 style={{ fontFamily: "var(--font-display)", fontSize: 72, fontWeight: 400, letterSpacing: "-0.035em", margin: "16px 0 12px", fontVariationSettings: "'opsz' 144, 'SOFT' 50" }}>
        Goals
      </h1>
      <p style={{ fontSize: 17, color: "var(--fg-2)", margin: "0 0 8px", maxWidth: 720 }}>
        Named shared pursuits. Anyone can declare one. Anyone can fork a branch toward it — or invent a new one.
      </p>
      <p style={{ fontSize: 14, color: "var(--fg-3)", margin: "0 0 40px", maxWidth: 720 }}>
        Three live today. Thousands soon — these are just seeds.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {DEMO_GOALS.map((g) => <GoalCard key={g.id} goal={g} onOpen={(gg) => setOpenGoalId(gg.id)} />)}
      </div>

      <div style={{ marginTop: 48, background: "var(--bg-inset)", border: "1px dashed var(--border-2)", borderRadius: 14, padding: "28px 32px", textAlign: "center" }}>
        <RitualLabel>Don't see your goal?</RitualLabel>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 500, letterSpacing: "-0.01em", margin: "10px 0 14px" }}>
          Declare a new one.
        </h3>
        <p style={{ fontSize: 14, color: "var(--fg-2)", maxWidth: 560, margin: "0 auto 18px", lineHeight: 1.55 }}>
          Name the pursuit. Sketch the outcome-gate ladder. Branches will come.
        </p>
        <Button variant="ghost">Propose a goal</Button>
      </div>
    </div>
  );
}

Object.assign(window, { Catalog });
