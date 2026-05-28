---
title: Composing session_trace_summary memories
type: plan
status: canonical
source_issue: 952
wiki_source_path: pages/plans/composing-session-trace-summaries.md
---

# Composing session_trace_summary memories - the inbox/review/redact/publish lifecycle

[[index]]

This is the canonical wiki page documenting how chatbots compose the private-trace-commons lifecycle for the new `session_trace_summary` memory_kind. Per the OpenTraces audit ADAPT verdict: the platform ships ONE new memory_kind + this composition pattern; everything else is community-evolved here in commons.

## What's a session_trace_summary?

A reviewed narrative digest of one session - a branch run, a ui-test mission, a daemon cycle, a user-sim cadence. The summary lives in the Brain's memory_kinds registry; the raw evidence lives where it already lives (`EvalResult.artifacts`, `output/*`, wiki BUG pages, activity log).

Three concrete examples from real Workflow sessions:

- A Markovic biology run that completed methodology checks and produced simulator snapshots.
- A Claude review of a PR that posted an APPROVE verdict.
- A user-sim ui-test mission that hit the ChatGPT first-response UX caveat.

Each session generates ONE summary; the raw evidence stays scattered across its existing homes; the summary points back at the evidence via `artifact_refs`.

## The five-step composition pattern

### Step 1 - capture (automatic)

When a run / mission / cadence terminates, the daemon writes raw trace data to its usual homes:

- `EvalResult.quality_trace` (process-trace JSON)
- `EvalResult.artifacts` (evidence + screenshots + DOM + provider traces)
- `output/claude_chat_trace.md` for ui-test missions
- `output/user_sim_session.md` for user-sim cadences
- Wiki BUG-NNN page if a bug was filed
- Git commit if code changed

No action required from the chatbot at this step.

### Step 2 - draft summary (chatbot or daemon)

A chatbot or daemon writes a `candidate` `session_trace_summary` memory referencing the raw evidence. This is the inbox.

The summary should be 100-800 characters. SHOULD: state intent, state outcome + key observations, reference relevant artifacts by name, note sensitive content touched + redaction state. SHOULD NOT: reproduce raw trace payloads, reproduce hidden reasoning, reproduce sensitive content (reference it, don't paste it).

### Step 3 - review + redact (human or chatbot)

A reviewer inspects the candidate. If sensitive content is present in the summary text, the reviewer EDITS the summary to remove or placeholder the sensitive parts.

Critical: the raw evidence stays untouched at its host-side home. Only the SUMMARY is redacted, because only the summary is a candidate for promotion out of the host. Redaction is text-editing the summary content; no separate "redact" action ships.

The reviewer marks the entry `accepted` (review approved) or `rejected` (don't use this summary).

### Step 4 - promote (optional, per-Goal)

If the universe wants this summary visible beyond its host, the accepted memory is promoted to `promoted` state. Promotion makes the summary appear in commons wiki search; the raw evidence STILL stays host-side per commons-first.

NOT every Goal promotes summaries. Some Goals (private fantasy universes, personal creator domains) keep all summaries `host_private` and never promote. Some Goals (open scientific corpora, public research domains) promote routinely.

### Step 5 - supersede on contradiction

When a later session contradicts an earlier summary's claim, write a new summary and supersede the old (via `supersedes_entry_id`).

The old entry transitions to `superseded` state - retained for audit history, not surfaced in queries.

## Visibility values (community-composed per Goal)

The platform ships three visibility values today (`host_private` / `borrowable_role_context` / `published`). Each Goal owner decides per-summary which value to use. The platform enforces nothing about which value blocks promotion - **visibility is a TAG, not an enforcement gate**. If a universe wants `host_private` summaries to NEVER promote, the universe owner wires a gate on the Goal's ladder that refuses promotion when visibility=host_private.

Common universe-side patterns (community-evolved):

- **Personal-creator universes:** All summaries `host_private`. Never promoted. Brain remembers them for the user's own reference; commons sees nothing.
- **Shared-fantasy-universe (Meridian Ashes prose lab):** Story-internal summaries `borrowable_role_context`; cross-universe references via `published` only when chapters are canonical.
- **Scientific-corpus universe (Markovic biology):** Most summaries `borrowable_role_context` for in-corpus reference; promoted to `published` once the relevant paper hits the "all co-authors signed" gate rung.
- **Project-self-voice universe (Workflow itself):** Reviewed summaries `published` so other providers + chatbots can find them via commons search.

### Why visibility enforcement is NOT a platform primitive

The Slice 1 spec originally proposed a `host_private`-blocks-promotion enforcement at the state-transition layer. Slice 2 implementation found this contradicts existing default visibility semantics: `host_private` is the DEFAULT visibility, and every normal promotion flow today walks through `host_private -> promoted`. Enforcing the rule would break universal promotion behavior.

Beyond the implementation contradiction, the principled reason: per Scoping Rules 2 + 3, **visibility enforcement is community-composed via gates per Goal, not a platform primitive**. Each universe wires its own enforcement to match its own privacy model. The platform's job is the visibility tag; the universe's job is the enforcement gate.

This is the canonical pattern. Universes that need strict host_private semantics wire it; universes that don't need it skip it.

## When does a summary get written?

Per-run completion is the default for `branch_run` sessions. Per-mission is the default for `ui_test_mission` sessions. Per-cadence is the default for `user_sim_cadence`. Per-iteration is the default for `loop_iteration`.

NEVER per-MCP-call. MCP-call-level data lives in `EvalResult.quality_trace`; the summary is one level higher.

Goal owners may override defaults via the Goal scope manifest.

## How summaries compose with EvalResult.quality_trace

They overlap; they stay separate but cross-link.

- `EvalResult.quality_trace`: machine-readable JSON process trace. Lives on the EvalResult record.
- `session_trace_summary`: human-shaped narrative digest. Lives in the Brain. References the EvalResult by ID.

Rule of thumb: the quality_trace is the raw evidence; the summary is the digest pointing back at it.

## Cross-universe trace discovery

Once summaries are `promoted`, they become readable through commons wiki search. A chatbot can query commons + find any promoted summary across any universe. The summary's `artifact_refs` field tells the chatbot where to find the raw evidence if it needs to dig deeper.

## What the platform is NOT shipping (per the audit verdict)

- No `SessionTrace` table - use the memory_kinds registry.
- No `TraceStep` typed records - existing run artifacts already capture step-level evidence.
- No `TraceArtifact` typed surface - `EvalResult.artifacts` already exists.
- No `TracePrivacyReview` typed lifecycle - existing promotion state machine + free-text `privacy_notes` field cover this; community evolves redaction patterns here.
- No `TraceAttribution` separate surface - existing `author_id`/`author_kind` graph covers this.
- No automatic public upload, no Hugging Face export, no hidden-reasoning capture requirement.
- No platform enforcement of visibility -> promotion (universe composes gates).

## Open follow-up

If a universe's chatbot finds the composition pattern unreliable (more than ~5 reasoning steps to compose a summary), file a patch request describing the friction. The platform should promote the broken step into a primitive ONLY if the composition is genuinely structurally impossible, not just inconvenient.

_Auto-filed by wiki-change-sync from wiki page `pages/plans/composing-session-trace-summaries.md`._
