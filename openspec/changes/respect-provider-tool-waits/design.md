## Context

Base ded0fb12 has the same runtime as deployed f5c5e5ec. Its real stream reader
kills known pending tools at the ordinary idle interval. Root's red tests at
4dca407f show two failures and one correct post-tool-idle control; existing
Windows suite passes98/skip1. Exact production run6ffec5e973734074 is a60s
failed run with30s protocol silence, committed side-effect state and an
indeterminate reservation, but no persisted tool phase. Do not replay it.

## Goals / Non-Goals

Goal: healthy identified tool work survives model-idle silence while failures
retain enough safe phase evidence to distinguish pending tools from later silence.
No global timeout increase, new MCP handle, authority change, provider choice,
automatic replay, workflow editing or historical-cause claim. No new dependencies.

## Decisions

1. Preserve native tool IDs from full assistant and partial content-block-start
   events; results reference tool_use_id. Pair identities rather than last event
   kind. Duplicate frames are idempotent; multiple/nested calls stay independent.
   Missing/malformed IDs earn no new allowance. IDs remain in memory, not public
   diagnostics. The protocol stays adapter-specific; waiting semantics do not
   depend on model names or tool names.
2. Pending tool work uses min(existing absolute cap,900s), matching the existing
   bounded native-tool convention. Ordinary model-idle, provider retry grace and
   absolute/cancellation behavior remain; terminal results clear pending work.
   Do not infer the provider emits regular tool heartbeats without a real trace.
3. Project tool_phase from an explicit admitted enum and last_progress_age_ms
   only when finite/nonnegative/non-bool into shared ProviderAttemptDiagnostic
   and all existing sanitized chain projections to the persisted run/read.
   Never copy arbitrary attempt_telemetry. No raw tool arguments/IDs, prompts,
   provider errors, credentials or reasoning enter these fields. Unknown omitted.
4. Preserve held invocation/no-blind-replay, consent, sandbox and provider health
   classification unchanged. A completed tool or successful retry is not proof
   that a different tool was pending when the historical attempt failed.

## Risks / Trade-offs

- Lost/malformed starts or results: no identity means no allowance; every extended
  wait still has its absolute backstop. Test duplicates, unknown completions,
  nested/parallel tools, post-tool silence, absolute cap and cancellation.
- Diagnostic leakage: explicit scalar/enum validators at the shared projection,
  with malicious strings, bool, NaN/Infinity and persisted held-error tests.
- Wrong incident attribution: keep the historical cause open. Live acceptance
  requires an app-agent-owned long-tool test and a rendered successful result;
  controlled stream tests are supporting evidence, not that final proof.

## Migration Plan

Optional diagnostic fields use existing JSON storage; no migration. Root owns
release: focused Windows/Linux tests, mirror, exact-head cross-family review,
CI, protected deployed SHA/canary, exact checklist prompt and ordinary app proof.
Sync/archive only after acceptance. Rollback prior image, never replay old runs.

## Review

Independent Fable61378 completed215s: ADAPT with agreement on ID-paired bounded
waiting plus safe persisted phase/age, tests A-G, and explicit non-attribution.
This design incorporates those conditions. Existing main concern has stale
production wording; update it with verified evidence, preserving unknown cause.
Protocol references: official Claude tool-call lifecycle uses id/tool_use_id
(https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
and repo captured CLI2.1.261 schema in
docs/reviews/2026-09-17-native-answer-model-shape.md. No heartbeat cadence assumed.
