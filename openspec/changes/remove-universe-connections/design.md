## Context

Existing HTTP remove already erases the secret, connection, grants, capabilities
and consents. It lacks app reachability and dependent model lifecycle. Fable 5.1
shape review September19 returned ADAPT; evidence is retained under docs/reviews.
This lane uses existing platform-held private vault custody, not a new custody mode.

## Goals / Non-Goals

Owner-controlled disconnect/reconnect without an LLM. Preserve private user
content, source choices, unrelated connections and history. No account reset,
upstream account/key deletion, user-workflow edits or per-provider exception.

## Decisions

- Reuse `remove_http` and its secret-free projection. Add same-origin owner app
  ingress with current home checks and observed incarnation, no new MCP handle.
- Serialize connection deposit/removal and hosted gestures per universe with a
  reentrant gesture lock. Keep exclusive assignment admission at authority
  mutation, never nest its deliberately nonreentrant lock around vault calls.
- Before destroying custody, revoke dependent work bindings, remove the source
  from accepted assignment membership, re-anchor retained sources if needed and
  republish their narrower assignment. Preserve their accepted scopes/ceilings.
  No remaining source means an `unassigned` tombstone retaining monotonic
  assignment identity. Delete connection custody in the same authority transaction
  so reusing a deterministic ledger id never revives old model approval.
- Definitions remain user configuration. Disconnect does not edit agent content.
  Re-anchoring changes only the server-owned provider reference at exact revision;
  last-source disconnect sets runtime status to configured, preserving its
  configuration and revision for explicit reconnection. Current helper inspection
  corrects the review's claim that set-serving changes revision: it does not.
- Reconnect is an explicit disconnected setup path, separate from strict pristine
  bootstrap. Capture the unique owned agent's current revision and require fresh
  model approval. Retained tombstone membership is not accepted model access.
- Partial cleanup leaves authority fenced and reports incomplete. Already launched
  remote effects may finish; never claim cancellation or automatically replay.

## Risks / Trade-offs

The gesture lock is process-local (current single daemon). Existing vault admission
is cross-process; full cross-process lifecycle serialization is follow-up hardening.
Incarnation checks refuse stale UI removal after redeposit. A disconnect that
removes the active root with other accepted sources re-anchors only within already
accepted membership; saved model preference remains unchanged and may need user
selection when it named the removed source.

## Verification

Focused owner/foreign owner, repeated remove, stale incarnation, mixed-source,
custody resurrection and guided reconnect tests; exact-head cross-family review;
Linux oracle for runtime/filesystem boundary changes; deployment and ordinary app
acceptance handled by lead only after both onboarding dependencies are ready.
