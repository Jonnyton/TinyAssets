## Context

The current run handler authorizes record access and explicit universe selection
before loading existing `run_events` and composing its snapshot. The status fold
discards timing and provider evidence. The raw stream handler is neither served
nor appropriate as-is: raw details include generated/private content and its
selector enforcement differs. No new storage or top-level handle is needed.

PLAN was read fully. This closes a generic evidence gap that users cannot safely
compose without access to stored observations; it does not choose their diagnostic
policy or workflow strategy. Custody is unchanged: existing universe run records
remain under their existing authorization/custody contract.

## Goals / Non-Goals

Goals: make useful stored node observations available through normal run reads;
retain evidence from successful predecessors after failures; preserve uncertainty,
scope, exact output access and provider portability.

Non-goals: new telemetry producers, raw transcripts, provider first-byte/launch
instrumentation, scheduler/cancellation changes, explaining historical stalls
without evidence, or a complete event browser. No private workflow modifications.

## Decisions

1. Extend the existing run snapshot with `node_activity` and a constant
   `activity_evidence` caveat. Keep `node_statuses`, output reads, tool signatures,
   accepted targets, generated-content envelope and adapters unchanged. The new
   helper is pure, in `tinyassets/api/run_activity.py`; the existing authorized
   `get_run` remains the only integration path. No raw stream handler is exposed.
   Alternative: a paginated event target would add routing, selectors and event
   API semantics before a user needs complete event order. This slice provides
   per-node evidence already in memory instead.

2. Fold events once into one metadata record per real node in existing declared
   order, including observed nodes not present in the current definition. Do not
   cap workflow shape or drop nodes silently. Preserve exact existing node IDs;
   bound newly exposed detail labels independently of graph size and keep
   the existing faithful bounded result envelope. Do not duplicate raw events or
   construct unbounded nested metadata. Exclude synthetic system rows, not
   arbitrarily user-named nodes merely because their name starts with underscores.

3. Metadata fields: `node_id`, existing `status`, `latest_step_index`,
   `latest_event_status`, `latest_event_at`, `local_started_at`,
   `local_finished_at`, `local_elapsed_seconds`, `start_events_observed`,
   `return_observed_at`, `return_step_index`, normalized `execution`,
   `legacy_provider_label`, `provider_latency_ms`, `provider_attempts`,
   `provider_degraded`, `failure_reason` and `failure_type`. Numeric observations
   must be finite and nonnegative, not booleans or numeric strings. Integer
   counts/steps are at most 2**53-1; degraded is boolean or unknown. Status labels
   are at most 80 characters, legacy provider labels 400, machine failure labels
   128. Invalid/oversized labels become null rather than being truncated into
   plausible values. Null means unavailable, never zero evidence.
   Omit free-form exception messages, prompt/response/previews, code/output,
   provider chains, effect payloads, authority or credential fields. No general
   redaction policy or provider-name enum is introduced.

4. Normalize `execution` through the existing strict
   `normalize_execution_receipt` helper. This is a newly constructed three-label
   projection, never copying a nested event object. Its model remains unknown if
   the provider did not report it. Do not promote legacy `provider_model` config
   metadata to an actual answering model. If a legacy provider label is exposed,
   label its provenance explicitly and leave actual-model knowledge unknown.

5. Time is local observation, not provider execution time. A `ran` row stamps its
   two times when recorded; its own span is not call duration. Compute local
   elapsed only when a valid start and terminal event pair is observed in order,
   resetting the pair on a subsequent start. Negative/nonfinite or missing
   values yield null. Keep the most recent returned-call receipt with its own
   step/time so a later retry or failure cannot misattribute it to the latest
   attempt. `start_events_observed` counts local starts, not provider attempts.

6. Explain that local start precedes concurrency/provider admission, a returned
   value may subsequently fail output validation, and no provider acknowledgment,
   first-byte record or exact subprocess-stop proof is present in this projection.
   Preserve these statements inside returned structured evidence so agents can
   answer honestly. No absent field is proof that a provider did not start.

7. Existing ACLs remain unchanged, including canonical readers already permitted
   by universe visibility/grants. Served reads stay universe-pinned; a public run
   in a different universe cannot escape the pinned selector. Metadata is not a
   new grant. Tests exercise both owner and selector boundaries before projection.

## Risks / Trade-offs

- Incorrect causal claims -> use local-observation names, receipt provenance,
  null unknowns and explicit caveats; test loops and terminal validation failure.
- New disclosure -> allowlist typed fields; omit free-form/nested detail; test
  adversarial payload sentinels and malformed metadata without altering uploads.
- Large graphs -> one small bounded record per node, no raw history expansion;
  verify outer adapter behavior remains faithful and bounded.
- Historical records have less evidence -> return honest unknowns; do not launch
  providers, replay runs or backfill invented timestamps to make reads look full.
- Useful metadata does not settle intermittent failures -> keep that broader
  issue open and use the new surface to guide any later instrumentation/fix.

## Migration Plan

No migration. Ship additive read behavior behind unchanged handles after focused
tests and independent exact-head review. Verify deployed SHA and public canary,
then send the exact checklist prompt once and ask the app to inspect an existing
failed run without rerunning it. Record what it can and cannot establish, inspect
organic-use evidence, sync the spec and archive this change. Rollback is the
ordinary reviewed revert/image rollback; stored evidence is untouched.

## Open Questions

Implementation settles scalar bounds above, excludes only the reserved
`__system__` row, and resets local timing on pending/running observations while
keeping prior return evidence separately tagged. Shape review is in REVIEW.md;
independent exact-head release approval and live acceptance remain pending.
