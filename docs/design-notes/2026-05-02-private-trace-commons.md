# Private Trace Commons — Slice 1 design

**Status:** Slice 1 design (per Claude review verdict ADAPT).
**Replaces:** the rejected 5-typed-surface proposal from the radar at `docs/audits/2026-05-02-frontier-repo-radar-3.md`.
**Authority:** Claude review `docs/audits/2026-05-02-opentraces-claude-review.md` (verdict: ADAPT — narrow to one memory_kind + wiki composition pattern).
**Touches:** Brain Module (memory_kinds registry + promotion state machine), Evolution & Evaluation Module (downstream consumer), Harness & Coordination Module (existing trace surfaces).
**Date:** 2026-05-19.

---

## What's IN scope

One new memory_kind `session_trace_summary` in the Brain Module's memory_kinds registry, plus a wiki composition-pattern page that documents how chatbots compose the inbox/review/redact/publish lifecycle using existing primitives.

That's it. Slice 1 ships:

1. A new entry in the `memory_kinds` registry: `session_trace_summary`.
2. The minimal schema for what fields a session_trace_summary memory record carries (see `docs/specs/2026-05-02-session-trace-minimal-schema.md`).
3. A wiki page in commons (path: `pages/plans/composing-session-trace-summaries.md`) documenting how chatbots compose the lifecycle.
4. No new MCP actions, no new tables, no new typed lifecycle surfaces.

## What's OUT of scope

Per the Claude review verdict, the original radar proposal's 5 typed surfaces are explicitly NOT shipped:

- ❌ No `SessionTrace` typed surface. (The salient trace data already lives in `output/claude_chat_trace.md`, `output/user_sim_session.md`, `.agents/activity.log`, `EvalResult.artifacts`, `EvalResult.quality_trace`, and wiki BUG-NNN pages.)
- ❌ No `TraceStep` typed surface. (Existing run artifacts already capture step-level evidence.)
- ❌ No `TraceArtifact` typed surface. (`EvalResult.artifacts` already exists.)
- ❌ No `TracePrivacyReview` typed surface. (Per Scoping Rule 3: privacy taxonomy is community-composed per universe; the platform doesn't ship one.)
- ❌ No `TraceAttribution` typed surface. (Existing `author_id` + `author_kind` attribution graph covers this; trace attribution is computable from tool-call sequence + actor identities.)
- ❌ No platform `experience_pool action=summarize` MCP action. (Composition pattern in wiki is the answer.)
- ❌ No automatic trace upload, no Hugging Face publishing path, no public export of any kind in Slice 1.

## The Brain Module memory_kind

The Brain Module's memory_kinds registry was established via open-brain v2 slice A (#904). Existing kinds (per `workflow/daemon_brain.py`):

- `semantic` — Stable facts, concepts, durable domain knowledge.
- `episodic` — Specific observed events, runs, source episodes.
- `procedural` — How-to knowledge, repeatable workflows, operating steps.
- `policy` — Rules, constraints, decision policies.
- `claim` — A checkable assertion needing provenance or revision.
- `preference` — Host/user/role preferences that steer behavior.
- `failure_mode` — Known ways work fails + guardrails that prevent repeats.
- `open_loop` — Unresolved follow-up, watch item, incomplete thread.
- `contradiction` — Conflicting claims/evidence needing reconciliation.
- `soul_proposal` — Candidate change to daemon's identity or role contract.

Slice 1 adds:

- **`session_trace_summary`** — A reviewed narrative summary of one session (an MCP call sequence, a daemon run, a ui-test mission, a user-sim cadence) suitable for human or chatbot inspection. Holds salient facts about the session (provider, model, task ref, outcome, artifact refs, attribution refs, visibility tag) without storing the raw trace payload itself (the raw payload lives in existing places: `output/*`, `EvalResult.artifacts`, wiki BUG pages).

The kind composes with the existing promotion state machine without modification: `candidate → accepted → promoted → rejected → superseded`. That IS the inbox/review/redact lifecycle the radar wanted — already shipped, just needs to be USED for this kind.

Storage: per Brain Module substrate, this lives in the daemon brain DB (host-side per Commons-first Rule 4). No platform-side storage of trace summaries.

## When does a session_trace_summary get written?

**Per-run completion as the default.** When a branch run terminates (success or failure), the daemon writes a session_trace_summary as a `candidate` memory.

**Per-mission for ui-test cadences.** When a `ui-test` mission completes, the user-sim discipline writes one summary per mission.

**Never per-MCP-call.** Too noisy. MCP-call-level trace data lives in `EvalResult.quality_trace` and `output/claude_chat_trace.md`; the summary is one level higher.

Goal owners may override these defaults via the Goal scope manifest (per the external-write authority design — host-locked 2026-05-19): a Goal can declare "summarize every MCP call" if its workflow genuinely needs that, but it has to opt in explicitly.

## How does session_trace_summary compose with EvalResult.quality_trace?

They overlap; they should stay separate but cross-link:

- `EvalResult.quality_trace` — JSON process-trace data captured during evaluator execution. Machine-readable. Lives on the EvalResult record.
- `session_trace_summary` (memory_kind) — Narrative summary fit for human/chatbot review. Lives in the Brain. References EvalResult IDs.

Rule: the quality_trace is the raw evidence; the session_trace_summary is the human-shaped digest pointing back at the raw evidence. Each EvalResult MAY have an associated session_trace_summary; not every quality_trace gets summarized (only the ones that earn promotion through the review lifecycle).

## The wiki composition pattern

A new commons wiki page (`pages/plans/composing-session-trace-summaries.md`) documents the lifecycle. The page walks through one concrete end-to-end example (see worked example below) and explains the composition. Community evolves the redaction patterns, the review heuristics, the per-domain conventions.

The pattern composes:

1. **Capture** — A run completes; daemon writes the raw trace evidence to its usual homes (`EvalResult.artifacts`, wiki BUG page if a bug was filed, `output/` for ui-test missions).
2. **Draft summary** — Daemon (or a chatbot via MCP) writes a `candidate` session_trace_summary memory referencing the raw evidence. This is the inbox.
3. **Review + redact** — Human or chatbot inspects the candidate. If sensitive content is present, the reviewer EDITS the summary to remove/placeholder the sensitive parts (the raw evidence stays untouched on its host-side home; only the SUMMARY is redacted because only the summary is a candidate for promotion). The reviewer promotes the candidate to `accepted` or rejects it.
4. **Promote (optional)** — If the universe wants this summary in the public commons (per the Goal's visibility policy), the accepted memory is promoted to `promoted` state. Promotion makes the summary readable through commons wiki search; the raw evidence stays host-side per Rule 4.
5. **Supersede on contradiction** — If a later session contradicts the summary, the new summary supersedes the old; the old enters `superseded` state but stays for audit.

All five steps use the existing promotion state machine (#904). No new lifecycle code.

## Worked example: Markovic publication session

Concrete walk-through (referencing the in-flight Markovic universe per BUG-089 + PR-130 in the wiki):

**Setup.** A run of the Markovic fingerprint RD branch executes against the simulated-biology pipeline. The run touches patient-shaped placeholder data (anonymized but still sensitive-by-default). The run completes with an EvalResult including `quality_trace` (JSON) and `artifacts` (snapshots of the simulator state).

**Step 1 — capture.** Daemon writes EvalResult to its usual home; `quality_trace` JSON; artifact snapshots in `output/`.

**Step 2 — draft summary.** Daemon writes a candidate session_trace_summary memory: `provider=codex-cli`, `model=gpt-5`, `task_ref=markovic_fingerprint_rd_v3`, `outcome=success`, `artifact_refs=[evalresult://run-abc123]`, `attribution_refs=[author::jonnyton, author::codex-cli]`, `visibility=universe_only` (default), `summary_text="Run completed. Methodology check passed; 3 simulator artifacts generated. Patient placeholders consistent with prior corpus."`

**Step 3 — review + redact.** Markovic universe's reviewer (could be the host or a designated chatbot) inspects the candidate. The `summary_text` mentions "patient placeholders" — that's domain-acceptable language but reviewer decides to add explicit redaction note: "Patient placeholders consistent with prior corpus. [No PHI exposed; only synthetic identifiers used.]" Reviewer promotes to `accepted`.

**Step 4 — promote (Markovic is a public scientific corpus).** Universe owner promotes accepted summaries to `promoted` once a paper-draft Goal hits the "all-co-authors signed" rung. The promoted summary becomes readable in commons wiki search; other research universes can find it via similarity search.

**Step 5 — supersede.** If a methodology refinement later contradicts the summary's claim ("methodology check passed"), the new summary supersedes the old. Both stay; the old is `superseded`.

The whole flow composes from existing primitives. No new platform code beyond the memory_kind registration.

## AcceptanceScenario interaction (lazy)

Per the OpenTraces audit open question #5: an AcceptanceScenario might want to assert "this trace summary contains evidence of X." Should `target_surface` on AcceptanceScenario include `session_trace_summary` as a value?

**Slice 1 answer: lazy.** Wait until the first AcceptanceScenario Slice 1 design actually surfaces this need. If it does, add `session_trace_summary` as a target_surface value at that point — small additive change, doesn't require Slice 1 here to anticipate it.

## What changes in code

1. `workflow/daemon_brain.py` MEMORY_KIND_REGISTRY: add `"session_trace_summary": "Reviewed narrative summary of one session; references raw artifacts, not raw payloads."` to the dict.
2. Update `VALID_MEMORY_KINDS` (frozenset) to include the new key (automatic if it's derived from the registry).
3. Plugin mirror at `packaging/claude-plugin/plugins/workflow-universe-server/runtime/workflow/daemon_brain.py`: same change.
4. Tests in `tests/test_daemon_brain.py`: one test asserts `session_trace_summary` is a recognized kind and can transition through the promotion lifecycle (uses the existing test_daemon_memory_lifecycle test pattern with the new kind).

Total code surface: ~6 lines per file (canonical + mirror) + one new test function. The wiki composition pattern is content, not code.

## Open follow-ups (post Slice 1)

- **Slice 2:** If real usage shows the composition pattern is unreliable (>5 reasoning steps for a chatbot to compose), promote one or more steps into a platform primitive. Default expectation: not needed.
- **AcceptanceScenario integration:** Lazy add when the first scenario needs it.
- **Cross-universe trace federation:** Out of scope. Each universe's Brain holds its own trace summaries; cross-universe discovery uses normal commons wiki search.
- **Hugging Face JSONL export:** Out of scope; per ADAPT verdict + Rule 4, no public export in Slice 1. Future slice (post-uptime, post-substrate) can revisit.

## How this respects the ADAPT verdict's specific REJECTS

| Audit REJECT | This design |
|---|---|
| No new `SessionTrace` typed primitive | ✅ no new typed surface — uses existing memory_kinds registry |
| No `TracePrivacyReview` typed lifecycle | ✅ uses existing promotion state machine; redaction is wiki-page edit by reviewer |
| No `TraceAttribution` separate surface | ✅ uses existing `author_id`/`author_kind` graph; trace attribution computable |
| No automatic public trace upload | ✅ promotion to commons is per-universe opt-in, not automatic |
| No hidden-reasoning-as-requirement | ✅ summary is narrative; raw payloads stay host-side |

## Verification (Slice 1 acceptance check)

- [ ] `session_trace_summary` appears in `workflow/daemon_brain.py::MEMORY_KIND_REGISTRY`
- [ ] Plugin mirror parity holds
- [ ] One new test in `tests/test_daemon_brain.py` exercises the kind through the promotion state machine
- [ ] Wiki composition pattern page exists at `pages/plans/composing-session-trace-summaries.md` with the worked example above
- [ ] No new MCP actions added
- [ ] No new tables added
- [ ] No public export path added
- [ ] Cross-link from Brain Module section of PLAN.md to this design note (small PLAN.md amendment in Slice 1, OR a follow-up; either works)

## Cross-frame consistency

- **Brain Module** — adds one memory_kind to the existing registry; composes with promotion state machine; no new architecture.
- **Commons-first (Rule 4)** — raw trace evidence stays host-side; only reviewed summaries are candidates for commons promotion; promotion is per-Goal opt-in.
- **Minimal primitives (Rule 1)** — one new memory_kind value, zero new typed surfaces.
- **Community-build over platform-build (Rule 2)** — redaction patterns, review heuristics, per-domain conventions are all community-evolved through the wiki page and remixable composition.
- **Privacy via community (Rule 3)** — no privacy taxonomy shipped; reviewer composes per-piece privacy decisions per Goal.
- **User capability axis (Rule 5)** — works for browser-only users (their MCP client reviews summaries the same way local-app users do); no local-app dependency.

All five scoping rules pass.
