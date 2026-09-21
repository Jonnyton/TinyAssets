## Context

Base7fdf6a70 (verified on origin/main September21 via check_primitive_exists sha).
The served adapter refuses effect-bearing add_node and effects/workspace updates;
the canonical branch updater already supports both fields. PLAN requires editable
compositions and no graph-size ceiling. Current sandboxed code runs by authorship,
not approval boolean; source approval records only who reviewed which source.

## Goals / Non-Goals

Goal: an owner changes an existing workflow's effect/workspace declarations from
the ordinary app, without rebuilding it or acquiring authority through editing.
No new handle, operation, sink, connection, consent, execution path, schema or
private workflow. Do not expand unrelated node-update fields or fix unrelated
concurrent patch CAS and cross-universe-of-one-author residuals in this slice.

## Decisions

1. Reuse write_graph patch -> canonical patch_branch staged validation/persistence.
   No second updater or recreate-the-branch workaround. Invalid batches save nothing.
2. Share effect-declaration validation between create/add/update. Preserve the
   two admitted sinks, array-of-strings shape, and existing single-sink-per-node
   packet-dispatch contract. Empty array or null clears. Omission preserves. Reject unknown
   sinks, malformed declarations and repeated sinks before persistence.
3. Add effect-bearing nodes through the existing sanitized add path. Remove the
   obsolete per-branch ceiling refusal; do not invent a replacement graph-size cap.
   Strip incoming author/approval/fork data just as creation does.
4. Reuse canonical workspace string/null clearing behavior and compiler ancestor,
   lease and sandbox checks. A declaration is not a live lease or a host path.
   Shape-invalid input refuses atomically; an unavailable/non-ancestor workspace
   still fails the established compile/run boundary rather than granting access.
5. Editing fires no effects and grants no authority. Runtime connection owner,
   destination consent, workspace admission, SSRF, sandbox and resource gates remain.
   Approval metadata cannot be supplied by an update; unchanged source retains its
   genuine source-review provenance, changed source clears it by the existing path.
   Do not reintroduce approval-as-execution-permission or gratuitously erase true
   source provenance merely because a declaration changed.

## Risks / Trade-offs

- Widening beyond creation grammar -> one shared declaration validator plus parity
  tests, real-store readback, rejected-batch no-change evidence and foreign-owner
  refusal. Keep existing dangerous fields refused.
- Changed declaration mistaken for consent -> test edit performs no dispatch,
  binds only existing authoring capabilities, and grants remain absent/unchanged;
  exercise runtime refusal without consent using existing runtime regression seams.
- Stale safety comments -> replace only touched misleading commentary; cite actual
  authorship/sandbox/consent boundaries. No new architectural policy is needed.
- Cross-author access and raw workspace paths -> preserve owner gate and runtime
  ancestor/lease validation; Linux oracle for the relevant workspace regressions.

## Migration Plan

No data migration. Review before code; focused regressions plus required CI,
plugin mirror, exact-head review, deploy SHA and public canary. Then send exactly
Retest your workflow checklist, followed if needed by a normal user request for
the app agent to repair its own existing workflow. Operator never edits it.
Rollback is the preceding image; no declarations are rewritten or removed.
Sync the canonical spec and archive only with deployed live acceptance.

## Open Questions

Independent Fable source/shape review approved this shape before implementation;
receipt: docs/reviews/2026-09-21-served-effect-edit-shape.md. Basic-safety conditions
are the shared declaration validator and persisted malformed/foreign refusal.
A green checklist without an actual effect edit will not close this capability.
