# session_trace_summary — minimal schema spec

**Status:** Slice 1 minimal schema (per `docs/design-notes/2026-05-02-private-trace-commons.md`).
**Authority:** Claude review ADAPT verdict (`docs/audits/2026-05-02-opentraces-claude-review.md`).
**Date:** 2026-05-19.

---

## Purpose

Specify the data shape carried by a `session_trace_summary` memory record in the Brain Module's memory_kinds registry. Slice 1 schema only — narrative summary fit for human/chatbot review, with references back to raw artifacts that live in their existing homes.

## Inheritance

A `session_trace_summary` is a `daemon_brain_entries` row (existing table, no schema migration needed) where `memory_kind = "session_trace_summary"`. The existing row schema covers identity, ownership, content, metadata, lineage, and promotion state. This spec defines the **content shape** (what goes in `content` + `metadata_json`) — not a new table.

## Fields (in `metadata_json`)

The structured fields are stored in the existing `metadata_json` column. Free-form narrative goes in `content`. All fields are optional unless marked required.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `session_id` | string | required | Stable identifier of the session being summarized. Format: provider-prefixed (`mcp-call:<call-id>`, `run:<run-id>`, `mission:<ui-test-mission-id>`, `cadence:<user-sim-cadence-id>`). |
| `session_type` | enum | required | One of: `mcp_call`, `branch_run`, `ui_test_mission`, `user_sim_cadence`, `loop_iteration`. Constrains what's expected in other fields. |
| `provider` | string | required | Acting provider identity: `claude-code`, `codex-cli`, `cursor`, `cowork`, `daemon`, `claude-ai-web`, `chatgpt-web`, etc. |
| `model` | string | optional | Specific model used if applicable (`claude-opus-4-7`, `gpt-5`, `o4`, etc.). |
| `task_ref` | string | optional | Goal/branch/node reference the session was advancing. Format: `goal:<goal-id>`, `branch:<branch-def-id>`, `node:<node-id>`. |
| `outcome` | enum | required | One of: `success`, `partial`, `failure`, `aborted`, `unknown`. |
| `artifact_refs` | list[string] | optional | URIs of raw artifacts the summary cites: `evalresult://<eval-id>`, `output://claude_chat_trace.md`, `wiki://bug-NNN`, `run://<run-id>`, etc. The summary REFERENCES; the raw artifacts stay where they are. |
| `attribution_refs` | list[string] | optional | Actors involved: `author::<id>`, `daemon::<id>`. Uses existing `author_id`/`author_kind` discriminator. |
| `evidence_tier` | enum | optional | One of: `direct` (summary author saw the session), `secondary` (summary derived from artifacts only), `synthesized` (multi-session merge). Helps reviewer judge trustworthiness. |
| `visibility` | enum | required | One of the existing `VALID_VISIBILITIES` values from `workflow/daemon_brain.py`: `host_private` (default; stays host-side unless promoted via the universe's own gate composition), `borrowable_role_context` (readable by other branches inside the universe), `published` (already promoted to commons wiki). Universe-specific promotion gates are community-composed; see `pages/plans/composing-session-trace-summaries.md`. |
| `privacy_notes` | string | optional | Free-text note about redaction state, sensitive fields touched, reviewer cautions. Replaces the rejected `TracePrivacyReview` typed surface. |
| `cost_estimate` | object | optional | Optional cost data: `{tokens: <int>, provider_cost_usd: <float|null>, wall_time_seconds: <int>}`. Aligns with cost-ledger READ surface (#906/04b5e86). |
| `superseded_by` | string | optional | Set on `superseded` state transitions; references the entry_id of the newer summary. |

## Field in `content` column

Free-text narrative summary fit for human or chatbot review. Length guideline: 100–800 characters. Examples in the design note worked example.

The narrative SHOULD:
- State what the session set out to do.
- State what happened (outcome + key observations).
- Reference relevant artifacts by name.
- Note any sensitive content touched + redaction state.
- Be a STANDALONE digest — a reader should understand the session without opening the raw artifacts.

The narrative SHOULD NOT:
- Reproduce raw trace payloads.
- Reproduce hidden reasoning (`<thinking>` blocks, internal CoT).
- Reproduce sensitive content even when the reviewer is the universe owner — sensitive material is referenced ("contains 3 patient-placeholder records, all anonymized") not reproduced.

## Promotion state machine (existing — no change)

Per open-brain v2 slice A (#904), the existing state machine applies unchanged:

```
candidate → accepted → promoted → superseded
candidate → accepted → rejected
candidate → rejected
candidate → superseded
accepted → superseded
promoted → superseded
```

Terminal states: `rejected`, `superseded`. From `promoted`, only `superseded` is reachable (a promoted summary cannot be reverted; if it's wrong, a new summary supersedes it).

## Visibility-state interaction

`visibility` and promotion `state` are orthogonal. Both move independently; the platform ships no built-in enforcement coupling them.

| visibility | candidate | accepted | promoted | rejected | superseded |
|---|---|---|---|---|---|
| `host_private` (default) | OK | OK | OK (universe's gate may refuse) | OK | OK |
| `borrowable_role_context` | OK | OK | OK | OK | OK |
| `published` | OK | OK | OK (sticky once promoted) | OK | OK |

**Enforcement is community-composed per Goal**, NOT a platform primitive. (Retracted from the initial Slice 1 draft of this spec; see "Retracted enforcement rule" section below.) If a universe wants summaries with visibility=`host_private` to NEVER promote, the universe owner wires a gate on the Goal's ladder that refuses promotion when visibility=`host_private`. Per Scoping Rules 2 + 3, the platform ships the visibility tag; the universe ships the enforcement gate that fits its own privacy model.

The canonical composition pattern lives at `pages/plans/composing-session-trace-summaries.md`. See § "Visibility values (community-composed per Goal)" + § "Why visibility enforcement is NOT a platform primitive."

## Retracted enforcement rule

The initial Slice 1 draft of this spec (landed via #931) proposed: "when a write attempts to set state=`promoted` on an entry with visibility=`host_only`, the platform refuses the write." Slice 2 implementation (#933 / 65087dc) discovered two reasons to retract:

1. **Implementation conflict.** The default visibility for new memories is `host_private` (per `workflow/daemon_brain.py:446`). Every normal promotion flow today walks through `host_private → promoted`. Enforcing the proposed rule would break universal promotion behavior for all memory_kinds, not just `session_trace_summary`. The existing `test_daemon_brain_smoke_roundtrip` smoke test failed against the enforcement.

2. **Scoping rules.** Per Scoping Rule 2 (community-build over platform-build) and Rule 3 (no platform privacy taxonomy), visibility enforcement IS the kind of policy community evolves per Goal. The platform ships the tag; the universe composes the gate. Even my own ADAPT-narrowed proposal overshipped here.

The retraction is itself a worked example of Scoping-Rule-2 discipline: spec proposed enforcement; implementation found it broke existing flows AND violated the principle anyway; the enforcement is community-composed via gates.

## Cross-link to the Brain Module spec

The Brain Module section of PLAN.md (per PR #915, 41569b5) declares:

> **Substrate:** `workflow/memory/`, `workflow/retrieval/`, `workflow/knowledge/`, `workflow/learning/`, `workflow/storage/__init__.py` (memory_kinds + promotion state). Open-brain v2 slices landed 2026-05-19: A=memory_kinds registry, B=soul-guided dispatch read, C=treasury status read, D=bounded autonomous spend.

`session_trace_summary` is additive to the registry. No substrate change.

## Example record

A complete example for the Markovic worked-example from the design note:

```json
{
  "memory_kind": "session_trace_summary",
  "content": "Run of Markovic fingerprint RD branch v3 against simulated-biology pipeline. Methodology check passed; 3 simulator artifacts generated. Patient placeholders consistent with prior corpus. [No PHI exposed; only synthetic identifiers used.]",
  "metadata_json": {
    "session_id": "run:abc123def456",
    "session_type": "branch_run",
    "provider": "codex-cli",
    "model": "gpt-5",
    "task_ref": "branch:markovic_fingerprint_rd_v3",
    "outcome": "success",
    "artifact_refs": [
      "evalresult://run-abc123",
      "output://markovic-run-abc123/simulator-snapshots.tar"
    ],
    "attribution_refs": [
      "author::jonnyton",
      "author::codex-cli"
    ],
    "evidence_tier": "direct",
    "visibility": "borrowable_role_context",
    "privacy_notes": "Patient placeholders synthetic; reviewer confirmed no PHI in summary text or referenced artifacts.",
    "cost_estimate": {
      "tokens": 84320,
      "provider_cost_usd": 1.43,
      "wall_time_seconds": 247
    }
  },
  "promotion_state": "accepted"
}
```

## Acceptance checklist

A Slice 1 implementation passes acceptance when:

- [x] `session_trace_summary` appears in `workflow/daemon_brain.py::MEMORY_KIND_REGISTRY` with one-line description. *(Shipped via #933 / 65087dc.)*
- [x] Plugin mirror at `packaging/claude-plugin/.../runtime/workflow/daemon_brain.py` has the identical entry. *(Shipped via #933.)*
- [x] Existing promotion state machine accepts the new kind unchanged. *(Verified via the new lifecycle test.)*
- [x] At least one test in `tests/test_daemon_brain.py` covers candidate → accepted → promoted lifecycle on the new kind. *(Shipped via #933: `test_session_trace_summary_is_recognized_kind_with_full_lifecycle`.)*
- [ ] No new MCP actions added.
- [ ] No new SQL tables added.
- [ ] No platform-side public export of any session_trace_summary content.
- [x] Wiki composition-pattern page (`pages/plans/composing-session-trace-summaries.md`) exists with the Markovic worked example. *(Shipped via #952.)*

## What is NOT in this spec

Out of scope per the ADAPT verdict (drop list):

- ❌ `SessionTrace` table or typed surface
- ❌ `TraceStep` typed surface
- ❌ `TraceArtifact` typed surface (existing `EvalResult.artifacts` covers this)
- ❌ `TracePrivacyReview` typed lifecycle (existing promotion state machine + `privacy_notes` free-text field cover this; community evolves redaction patterns)
- ❌ `TraceAttribution` typed surface (existing `author_id`/`author_kind` covers this)
- ❌ Hugging Face / external trace export pipeline
- ❌ Automatic capture of every MCP call into a trace summary
- ❌ Cross-universe trace federation
- ❌ Hidden-reasoning capture requirement

Future slices can revisit any of these IF concrete usage proves the composition pattern is insufficient. Default expectation per the ADAPT verdict: not needed.
