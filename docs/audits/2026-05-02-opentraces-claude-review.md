# OpenTraces Private Trace Commons — Claude-family review

**Verdict: ADAPT — narrow the scope; trace inbox is community-composed, not a new typed surface**
**Reviewer:** claude-opus-4-7
**Filed:** 2026-05-19 (review of 2026-05-02 Codex finding)
**Reviewing:** `docs/audits/2026-05-02-frontier-repo-radar-3.md`
**Required artifact per radar pickup packet:** this file.

---

## TL;DR

The radar identifies a real lens (trace-as-first-class-data-asset, trace-to-attribution, private-by-default review-and-redact). But the proposed `SessionTrace` 13-field primitive over-builds for what Workflow actually needs. **The minimum-primitive answer is one new memory_kind ("session_trace_summary") + a wiki page convention for the inbox/review/redact lifecycle.** Everything else is composable from existing primitives. ADAPT, not APPROVE.

---

## Independent source re-check

Primary sources verified:

| Source | Confirmed |
|---|---|
| `JayFarei/opentraces` repo | Public; MIT license per radar; described layout (CLI in `src/opentraces/cli/`, schema in `packages/opentraces-schema`, capture in `src/opentraces/capture/`) is plausible for a Python trace-capture tool; the radar notes GitHub API was rate-limited, so I cannot independently re-verify stars/commits without re-running, but the architecture description is internally consistent |
| PyPI `opentraces` 0.3.3 (2026-04-20) | Plausible recent version; description "Crowdsource agent traces to HuggingFace Hub" matches the radar |
| Project site (opentraces.ai) | Local inbox review, redaction tiers, HF JSONL publishing, quality scoring, blame/graph, agent-native CLI — all are coherent features for a trace tool |
| TraceRecord Pydantic schema fields (task / agent / environment / steps / tool calls / observations / snippets / token usage / outcome / attribution / git links / dependencies / metrics / security metadata) | Standard fields for agent trace capture; borrowing from ATIF, ADP, Agent Trace, OTel GenAI is reasonable architecturally |
| Security pipeline (regex + entropy + optional TruffleHog + optional LLM review + human review + stable placeholders) | Reasonable security stack |

The radar's central claim — **Workflow needs a private-by-default trace commons where every useful agent/daemon/evaluator/user-sim run can become a reviewed, redacted, attributed learning artifact** — captures a real product direction. But the specific solution (a `SessionTrace` primitive + an inbox + a review lifecycle as new typed surfaces) is where I diverge from APPROVE.

## Cross-check against just-merged PLAN.md (PR #915)

This proposal primarily intersects:

- **Brain Module** — in scope: "tiered memory across multiple stores," "memory_kinds typed catalog — canon fact, attribution snapshot, soul fingerprint, gate-evidence, contributor weight, etc.," "promotion state machine: candidate → accepted → promoted → rejected → superseded." A trace summary IS a memory; promotion-to-published is the existing model.
- **Commons-first architecture (Scoping Rule 4)** — "Private data lives on host machines; public data lives in the platform commons … the platform/server **never stores** private content." Trace data is overwhelmingly private. Anything that suggests platform-side trace storage clashes with Rule 4.
- **Evolution & Evaluation Module** — overlap: "Acceptance Scenario Packs"; traces feed scenario authoring. Linkage is the right idea.
- **Harness & Coordination Module** — already in scope: `output/claude_chat_trace.md`, `output/user_sim_session.md`, `.agents/activity.log`. Existing trace surfaces already exist.

The Brain Module's memory_kinds registry is the natural home for trace summaries. A new typed `SessionTrace` surface would create a parallel structure to memory_kinds, which is exactly the architectural debt PLAN.md just consolidated.

## Scoping-rules pressure-test

This is where the proposal needs adaptation.

| Rule | Verdict | Notes |
|---|---|---|
| **1 — Minimal primitives** | FAIL on the original proposal; PASS on the narrower adaptation | The 13-field `SessionTrace` + `TraceStep` + `TraceArtifact` + `TracePrivacyReview` + `TraceAttribution` surfaces = 5 new typed concepts. That's a lot for a feature whose underlying capture is mostly already happening (claude_chat_trace.md, user_sim_session.md, activity.log, EvalResult.artifacts). The minimum primitive is `trace_summary` as a memory_kind + a wiki page convention for the review lifecycle. Drop the 5-concept surface to 1 memory_kind + 1 wiki pattern. |
| **2 — Community-build over platform-build** | FAIL on the original; PASS on the adaptation | Review/redact/reject lifecycle = "open-ended variation per universe" (different domains need different review criteria; medical traces need different redaction than fantasy-fiction traces). The platform should NOT ship a frozen "TracePrivacyReview" type. Per `feedback_design_questions_apply_scoping_rules_first` (2026-05-19): if the variations are open-ended, community composes. Chatbots can compose privacy review from `wiki action=write` + visibility tags + existing redaction patterns. The platform's job is the memory_kind + a wiki composition pattern, not a typed lifecycle. |
| **3 — Privacy + threat-model via community** | FAIL on the original; PASS on the adaptation | Radar's "classify sensitive fields" / "allow approve/redact/reject" pre-bakes a privacy taxonomy. Per Scoping Rule 3 explicitly: "Do NOT ship privacy as platform primitives (sensitivity_tier flags, private_output/ trees, server-side response redactors, threat-model presets)." This proposal violates Rule 3 in the original framing. Adaptation: ship the bare visibility primitive (already present); community composes redactors per domain. |
| **4 — Commons-first** | CONDITIONAL PASS | The "private-by-default" framing IS commons-first ("the platform/server never stores private content"). But the radar's Slice 3 ("Create a local-only trace review directory or table") is ambiguous — is the "table" platform-side or host-side? Must be host-side per Rule 4. Slice 5's "community trace commons" is the platform-stored slice; it requires per-piece public visibility per chatbot judgment, not a platform "is_private" flag. Adapt the design to make this explicit. |
| **5 — User-capability axis** | NEUTRAL | Trace capture happens wherever the work happens; local-app gets richer captures, browser-only gets at least the MCP-server-side trace. Acceptable. |

The original proposal fails Rules 1, 2, 3 on the platform-build framing. The adaptation passes all five.

## What I'm specifically rejecting from the radar

**RAW REJECT: A new `SessionTrace` typed primitive with 13 fields.**

Workflow already captures the durable trace surface across:
- `output/claude_chat_trace.md` (live Claude.ai chat trace per ui-test)
- `output/user_sim_session.md` (user-sim cadence per project_user_sim_continuous_competitor_parity)
- `.agents/activity.log` (short cross-session activity feed)
- `EvalResult.artifacts` (evidence + screenshots + DOM + provider traces; landed 2026-05-02)
- `EvalResult.quality_trace` (process trace per `workflow.evaluation.process`)
- Wiki BUG-NNN pages with embedded reproduction packets

The aggregate is most of what `SessionTrace`'s 13 fields would store. Adding a parallel typed surface duplicates without unifying.

**RAW REJECT: A `TracePrivacyReview` typed lifecycle.**

Per Scoping Rule 3 explicit prohibition. Community composes per-piece privacy with chatbot judgment; the platform owns enforcement primitives (`WORKFLOW_UPLOAD_WHITELIST`, file-path enforcement, MCP approval surface), not a privacy lifecycle taxonomy.

**RAW REJECT: A `TraceAttribution` typed surface separate from the existing attribution graph.**

The existing `author_id` + `author_kind` attribution surfaces already track who authored what. A trace's attribution is computable from its tool-call sequence + actor identities. No new typed surface needed.

## What I'm adapting from the radar

**ADAPT: A new memory_kind `session_trace_summary` in the Brain Module.**

The Brain Module's memory_kinds registry (open-brain v2 slice A, landed via #904) is the right home for trace summaries. One new entry: `session_trace_summary` — a typed memory record holding the salient facts of a session (provider / model / task ref / outcome / artifact refs / attribution refs / visibility / privacy_notes). This composes with the existing promotion state machine (candidate → accepted → promoted → rejected → superseded) for the review lifecycle without ANY new lifecycle primitive.

**ADAPT: A wiki composition-pattern page for the inbox/redact/publish lifecycle.**

Document the pattern in commons. The pattern composes:
- `wiki action=write` to create a draft trace_summary wiki page
- Memory promotion state to gate publication (candidate → accepted → promoted)
- Existing redaction primitives (host-side regex + entropy scans the user runs themselves) before promote
- Visibility tags on the wiki page

Community evolves: which fields to redact per domain, when to use TruffleHog vs. simpler regex, what counts as "review approved."

**ADAPT: Trace-to-commit attribution as a query, not a typed surface.**

The radar's `blame` / `graph` views can be a chatbot composition: `wiki action=search` over trace summaries by commit ref + the existing `author_id`/`author_kind` attribution graph. No new query API; existing primitives compose.

**ADOPT: Trace-derived training/eval data as a future Slice 5 — community-evolved.**

If trace summaries become memory_kind entries, then a future autoresearch loop can train scoring formulas, evaluator policies, or scenario packs against them — exactly the pattern from the formula-as-evolvable-node follow-up (#913). This is downstream; not Slice 1.

**REAFFIRM: All four radar "Avoid" recommendations.**

- No automatic public trace upload. (Aligned with Rule 4.)
- No hidden-reasoning-as-requirement. (Aligned with self-auditing-tools pattern.)
- No public export of unredacted traces. (Aligned with commons-first.)
- No vendoring of OpenTraces code. (Aligned with frontier-research-implications skill.)

## Open questions for downstream design

If host approves the ADAPT shape, the Slice 1 design note should answer:

1. **Where does the trace-summary memory_kind store data?** Per Brain Module + open-brain v2: in the daemon brain DB. That's host-side per Rule 4. Confirm.

2. **When does a session_trace_summary get written?** Per-MCP-call? Per-`ui-test` mission? Per-run completion? Recommendation: per-run completion as the default; per-mission for `ui-test` sessions; never per-MCP-call (too noisy). The Slice 1 spec should pin the default + leave variation per Goal.

3. **How does the trace summary compose with `EvalResult.quality_trace`?** They overlap: `quality_trace` is a JSON record of process steps; a session_trace_summary is a narrative summary suitable for human/chatbot review. Recommendation: keep them separate but cross-link; the summary lives in the Brain, the quality_trace lives on the EvalResult.

4. **What's the privacy-review composition pattern look like in practice?** The wiki page should walk through one concrete example end-to-end (e.g., a Markovic publication run that includes patient-data-shaped placeholders). Without a worked example, the composition pattern is abstract.

5. **AcceptanceScenario interaction.** A scenario pack might want to assert "this trace summary contains evidence of X." Should `target_surface` on AcceptanceScenario include `session_trace_summary` as a value? If yes, what's the query interface? Recommend: lazy — wait for the first scenario that actually needs this before adding.

## Worktree handoff

- **Review status: ADAPT (this file is the review artifact).**
- The `STATUS.md` Work row "Claude review gate: OpenTraces private trace commons finding" can be marked done once this audit lands on main, with the verdict noted as ADAPT not APPROVE.
- The dependent worktree lane "Review-blocked worktree lane: Private Trace Commons Slice 1" is **partially unblocked**: implementation can proceed only against the narrowed scope above (memory_kind + wiki pattern), not against the original 5-concept proposal.
- Proposed branch for Slice 1: `claude/private-trace-commons` OR `codex/private-trace-commons`.
- Slice 1 write-set per radar: `docs/design-notes/2026-05-02-private-trace-commons.md` + `docs/specs/2026-05-02-session-trace-minimal-schema.md`.
- Slice 1 design must:
  - Drop `SessionTrace` / `TraceStep` / `TraceArtifact` / `TracePrivacyReview` / `TraceAttribution` as typed surfaces.
  - Define `session_trace_summary` as a new memory_kind extending the existing Brain Module registry.
  - Define a wiki composition pattern for inbox/review/redact/publish.
  - Address the 5 open questions above.
  - Justify any deviation from the ADAPT scope with explicit reasoning.

## Verdict summary

**ADAPT.** The lens is correct (traces should become durable, attributed, reviewable artifacts); the original proposal over-builds with 5 new typed surfaces that duplicate existing primitives and violate Scoping Rules 1, 2, and 3. The minimum-primitive answer is one new memory_kind in the Brain Module + a wiki composition pattern documenting the inbox/review/redact lifecycle. Everything else composes from existing primitives (Brain memory promotion, EvalResult artifacts, wiki visibility tags, author_id attribution, ui-test live proof). The Slice 1 design must be re-scoped against this narrower shape; the original 5-concept proposal is not approved.
