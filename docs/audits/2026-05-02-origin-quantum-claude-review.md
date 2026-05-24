# Origin Quantum Optional Capability Pack — Claude-family review

**Verdict: DEFER (concur with navigator memory recommendation)**
**Reviewer:** claude-opus-4-7
**Filed:** 2026-05-19 (review of 2026-05-02 Codex proposal)
**Reviewing:** `docs/design-notes/proposed/2026-05-02-origin-quantum-workflow-integration.md`
**Prior independent review:** `.claude/agent-memory/navigator/2026-05-02-origin-quantum-review.md` (navigator session-d, 2026-05-02; recommended DEFER)
**Required artifact per radar pickup packet:** this file.

---

## Context

This is the only one of the four 2026-05-02 review-gate audits where the design note ACTUALLY EXISTS on disk (the other three reference design notes that were never written). I read both the design note + the navigator's prior independent review. My job is to issue the formal Claude verdict.

The navigator already wrote a thorough DEFER review 17 days ago. This audit re-checks that work + applies the just-merged PLAN.md restructure (PR #915) + the new scoping-rules-first feedback (2026-05-19).

## Independent source re-check

Primary sources verified:

| Source | Confirmed |
|---|---|
| Origin Quantum (OriginQ) | Real Chinese quantum computing vendor; pyqpanda3 is their Python SDK; SDK exists on PyPI; geopolitical context (China-based, NATO export-control considerations) is real |
| Design note (`docs/design-notes/proposed/2026-05-02-origin-quantum-workflow-integration.md`) | Exists on disk; 402 lines; status: "proposed direction (gated on Claude review)" |
| Navigator memory (`.claude/agent-memory/navigator/2026-05-02-origin-quantum-review.md`) | Exists; 88 lines; recommended DEFER + move to `proposed/` (which has happened) |
| Capacity Grant + Credential Broker (`docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md`) | Referenced but NOT yet in PLAN.md typed vocab; navigator pre-review flagged this gap |
| OptimizationRun substrate | Slice 2 not yet drafted; navigator's pre-review just set the Rule-1 bar |

The design's internal logic is sound: quantum results map to existing `EvalResult` (avoiding a new evaluator primitive), `QuantumTask` is artifact-only inside OptimizationRun (avoiding premature table promotion), `workflow[quantum]` extras pattern matches existing optional-dep convention.

But the design depends on two unbuilt primitives (Capacity Grant + OptimizationRun), names one specific vendor (Origin Quantum + pyqpanda3) in its `workflow/quantum/providers/originq.py` tree, and has no current user pull. These are the three concerns the navigator flagged. I concur with each.

## Cross-check against just-merged PLAN.md (PR #915)

Origin Quantum primarily intersects:

- **Evolution & Evaluation Module** — in scope: the `Evaluator` primitive that "unifies fantasy judges, autoresearch metrics, moderation rubrics, real-world outcomes, and discovery ranking." A quantum-result-as-EvalResult IS the right shape (and the design correctly defers to this). PASS at the principle level.
- **Providers Module** — overlaps: "Pick the best provider per role" + "fallback chain correctness." Origin Quantum is a provider; the multi-vendor matrix concern lives here.
- **Distribution & Discoverability Module** — in scope: "Software surface is declarative and multi-layer-authorized … Nodes declare `required_capabilities` … missing software auto-installs (host-policy gated) … `external_tool_node`." Quantum compute SHOULD compose into this existing software-capability surface, NOT a parallel `quantum/` capability pack. **The design note doesn't reference this PLAN.md surface AT ALL.** Major omission.
- **Open Tensions** (PLAN.md bottom) — "Postgres-canonical vs GitHub-canonical is the largest unresolved architectural decision." Origin Quantum sits behind that decision; making quantum-execution commitments before catalog-canonical is settled is exactly the premature-scoping pattern.

The PLAN.md restructure makes the "compose into existing software-capability surface, not a parallel surface" rule explicit. The Origin Quantum design ships a parallel surface. This is fixable in a future re-design but the current design note does not address it.

## Scoping-rules pressure-test

Applying all five rules + the 2026-05-19 design-questions-scoping-rules feedback:

| Rule | Verdict | Notes |
|---|---|---|
| **1 — Minimal primitives** | CONDITIONAL PASS | The design correctly refuses a new EvaluatorKind. But it introduces `QuantumTask` artifact schema (10 fields) + `quantum/` capability pack + `workflow[quantum]` extras + `workflow/quantum/providers/originq.py` tree. The "promote-only-if-needed" guardrail is there; the conditional pass survives only if that guardrail holds. The deeper issue: per the just-landed Distribution Module, the canonical mechanism is `required_capabilities` + `external_tool_node`, not a `quantum/` capability pack. **The design ships a parallel surface, violating the Module Layout commitment.** |
| **2 — Community-build over platform-build** | PASS in principle, FAIL on the vendor choice | Optional-dep pattern is correctly community-build-friendly. But the `providers/originq.py` shape pre-picks Origin Quantum as THE first vendor, foreclosing community-composed multi-vendor evaluator chains. The community-build answer is: ship one quantum-execution `external_tool_node` template (composed from existing primitives), let community evolve provider-specific evaluators (Origin, IBM Qiskit, Rigetti, AWS Braket, Azure Quantum, Google Cirq, future zk-proof backends). The design picks a winner instead of shipping a substrate. |
| **3 — Privacy + threat-model via community** | FAIL | The design enumerates "circuit public only if inputs public; raw provider payload private-by-default" — this is a frozen privacy taxonomy that Scoping Rule 3 explicitly prohibits. The community should compose this per Goal (e.g., a research-paper Goal might require all circuits public for reproducibility; a corporate Goal might require all circuits private). |
| **4 — Commons-first** | CONDITIONAL FAIL on cloud path | Simulator path (local pyqpanda3) is host-side — commons-first compatible. Cloud QPU path sends data to Origin's servers (China-based per design note §Risks #10) — data leaves the host into a non-commons jurisdiction. The "data residency" risk is real and the design doesn't address it with explicit Capacity Grant policy gates. Cloud path violates Rule 4 until Capacity Grant exists with geopolitical-aware policy. |
| **5 — User-capability axis** | FAIL for cloud path; PASS for simulator | Local pyqpanda3 simulator: local-app users only (Python install). Browser-only users get nothing from the simulator path. Cloud QPU through MCP: browser-friendly IF Capacity Grant + Credential Broker existed — but those aren't built. Today the feature is local-app-only. The design mixes both paths as if equivalent; should explicitly tier them. |

Three FAILs out of five (Rules 2 vendor lock, 3 privacy taxonomy, 4 cloud commons). The design needs significant re-scoping before it can pass even the principle bar.

## Cross-check against the navigator's prior review

The navigator (session-d, 2026-05-02) recommended:
1. Move design note from `active/` → `proposed/` (or `ideas/PIPELINE.md`) ✅ **Already done** (file is at `docs/design-notes/proposed/...`)
2. Cite premature-scoping as biggest concern ✅ **I concur**
3. Cite vendor-lock as second concern ✅ **I concur**
4. Cite real-world-effect tension as third concern ✅ **I concur**
5. Cite OptimizationRun coupling as risk ✅ **I concur**
6. Cite `external_tool_node` / `project_node_software_capabilities` compatibility gap ✅ **I concur AND strengthen this** — the new PLAN.md Distribution Module makes this rule explicit; the design ships a parallel surface that violates it

Navigator memory also flagged a meta-issue: Codex wrote into navigator-scope agent-memory. That's a session-d coordination issue, not material to the design verdict. Out of scope for this audit.

## Open questions for the host (if you ever do reconsider this)

If quantum compute moves from "post-uptime, optional capability pack" to actively-in-flight, the design needs to address:

1. **Multi-vendor abstraction first.** Cataloging IBM Qiskit / Rigetti / AWS Braket / Azure Quantum / Google Cirq with their tradeoffs, before any vendor-specific code lands. The design should be `external_tool_node`-compatible quantum execution, not a `workflow/quantum/` surface.

2. **Capacity Grant + Credential Broker as a prerequisite.** Per the MCP host customer matrix model, the cloud-QPU path needs explicit credential-broker policy. The design references `capacity_grant_ref` and `executor_backend=origin_quantum_cloud` but those concepts don't exist yet. Build the substrate first.

3. **Real user pull.** ASI-Evolve has Mark wanting `change_loop_v1`; OpenTraces has the real cross-provider trace surface that already exists; AcceptanceScenario has live ui-test as the immediate downstream consumer. Quantum has none of this. The design should wait until a user (chatbot session) actually asks for quantum compute.

4. **Geopolitical / export-control story.** Origin is China-based. Default users are in NATO countries with chatbot subscriptions. Enterprise compliance is real; consumer compliance (ITAR, export-control) is non-trivial. Either ship explicit Capacity Grant policy gates, or pick a multi-vendor-first abstraction so users can choose non-Origin backends.

5. **Privacy taxonomy.** Drop the "circuit public if inputs public" pre-baked rule. Community composes per Goal.

## Worktree handoff

Per the radar pickup packet (referenced indirectly through the design note + STATUS Work row):

- **Review status: DEFER (this file is the review artifact).**
- The `STATUS.md` Work row "Claude review gate: Origin Quantum optional capability pack" can be marked done once this audit lands on main, with the verdict noted as DEFER.
- The dependent worktree lane "Review-blocked worktree lane: Origin Quantum Slice Q0/Q1" remains **BLOCKED**. The verdict is DEFER, not adapt; implementation should not proceed.
- Action: the design note can stay in `docs/design-notes/proposed/` as a record. Future re-consideration requires (a) Capacity Grant + OptimizationRun primitives landing in PLAN.md and code, (b) explicit multi-vendor matrix in the design note, (c) explicit user pull, (d) geopolitical/export-control policy story.

## Verdict summary

**DEFER.** Concurring with the navigator's 2026-05-02 prior review. The design's internal logic is sound (correctly defers to EvalResult, refuses new evaluator primitive, uses optional-dep pattern), but it depends on two unbuilt primitives (Capacity Grant + OptimizationRun), pre-picks one vendor (Origin Quantum) when multi-vendor matrix should come first, violates Scoping Rules 2/3/4 in concrete ways, and lacks current Workflow user pull. Move-to-`proposed/` already happened; this audit pins the dependency chain. Re-consideration requires the substrate primitives + multi-vendor framing + real user pull + geopolitical policy.

The frontier-radar lens that produced this finding is good (radar-mode is useful for catching adjacent capabilities). The specific bet on Origin Quantum is premature.
