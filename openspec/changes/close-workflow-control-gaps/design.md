## Context

September 9 UTC, source based on c2ed4534 with runtime 8f1b4760. The engine
wrapper delegates to canonical handles, but manually narrows operation/field
sets. Legacy api/runs already implements output reading and cancel requests.
The primitive checker reports CLEAN for these action names because it misses
their dispatcher shape; direct source inspection overrides that false negative.
No new implementation of cancellation or output storage is justified.

Full PLAN read before design. Existing account/universe custody and identity
remain unchanged. The canonical handles already own execution control.

## Goals / Non-Goals

Goal: close all five reported workflow lifecycle gaps through shared platform
capabilities, with the app agent constructing and repairing its own workflows.
Non-goals: new top-level handles, another execution/queue system, arbitrary
operator workflow edits, schema/PLAN changes, cross-universe authority, provider
policy changes or completion claims for unfinished resource consolidation.

## Decisions

1. **One edit vocabulary.** The actual operation is `update_node`; error/tool
   guidance must teach that operation and its real payload, not `patch_node`.
   Relational tests cover emitted advice against the served validator and a real
   owned branch write/read. This slice retains existing field validation and
   authority restrictions; it repairs the five guidance strings and provides
   actionable unknown-operation guidance. Broader field parity requires its own
   verified current safety premise and is not silently enabled here. No second
   compatibility operation is needed merely to preserve incorrect prose.
2. **Ancestry is not HTTP-response presence.** EffectChain.prior_effects currently
   derives from `results`, populated only for authenticated HTTP calls. Workspace
   push/discard uses membership there as ancestry, so a real workspace ancestor
   is absent. Pass the compiler's trusted ancestor relation separately through
   workspace dispatch to the mount resolver. Do not populate fake HTTP responses,
   disable ancestry checks, accept packet-supplied ancestry, or serialize mount
   descriptors. Preserve graph-node IDs (not shared definition IDs), run-owned
   mounts, sibling exclusion and lease/outbox cleanup semantics. Migrate internal
   callers/tests together instead of retaining two competing ancestry authorities.
3. **Output inspection uses existing stored output.** Add `read_graph` target
   `run_output` with an optional field selector, routed to existing get_run_output.
   Ordinary `run` read includes a compact output-field catalog and tells callers
   how to fetch it. Generated output remains untrusted content in the served
   wrapper. Enforce run/universe matching before any disclosure in pinned calls;
   existing ACL is also required. Apply this match to the existing run read too,
   not just the newly reachable output/cancel paths. No new result store. For a
   selected field, strings are read verbatim; other values serialize once as
   Unicode-preserving JSON. Return code-point offset, length, total_chars,
   truncated and next_offset; include the exact typed value only when the whole
   field fits. Catalogs contain names/types/sizes, never hidden previews. Preserve
   exact values across bounded continuation instead of silently truncating them.
   The new graph route always requests bounded formatting from the existing
   handler; the unadvertised legacy extensions response remains compatible.
   Selected-field chunks default to 8192 and cap at 32768 code points; catalogs
   page 64 field names/types/serialized sizes, using output_offset as field index
   when no field is selected. These are response bounds, not output-storage caps.
4. **Record the failing node at execution.** Code exceptions currently reach the
   generic run-failure handler without recording a failed node event. Correct
   the node lifecycle by emitting the existing failed event on the plain code
   failure branch, with the same identity as its starting event; normalize both
   to graph-instance identity at the wrapper that knows that identity;
   preserve the original exception and cancellation/timeout classifications.
   Do not infer that every running parallel sibling failed, or rewrite historical
   events on read. Existing precise effect/timeout failures must not regress.
   Normalize node_id on propagated CompilerError instances too: timeout/empty/
   effect failures are converted to terminal events in the runner, outside the
   inner event sink. Preserve the exception object, type and message.
5. **Cancellation is control, not a new run.** Add run_graph `operation` default
   `run` plus `run_id`; `cancel` uses existing cancellation storage/runner checks,
   never admission/provider launch. Reject ambiguous start/cancel/trigger arguments.
   Served calls pin universe and actor and require actual record membership plus
   write access; canonical calls honor their existing ACL and explicit graph scope.
   A terminal run returns its actual status without inserting a new cancel row;
   an accepted request reports actual current state and cancel_requested=true,
   not fabricated terminal success. Test queued and in-flight code cancellation
   through the real runner; describe provider/effect cooperative limits honestly.
   Real in-flight child proof found NodeCancelledError inherited a constructor
   that rejected its node_id keyword. Give it the same explicit identity-bearing
   constructor as the other node exceptions so cancellation stays cancelled,
   not TypeError/failed. Insert cancellation conditionally on nonterminal run
   state in one SQL statement to cover a concurrent finish without a schema change.

   Scope-gate verification found legacy cancel_run classified as admin, so the
   live resolve-always provider would reject an ordinary owner even though dev
   tests passed. Classify cancellation as write, matching the owner-control
   contract and existing schedule pause/delete precedent. Before doing so,
   tighten cancel's legacy non-universe path to its recorded owner/actor: the
   historical broad non-universe write allowance must not become a new cross-user
   cancellation permission. Universe rows still require their write ACL, and
   pinned calls still require exact universe membership. No admin capability is
   granted to the served agent. Test with production-style scope enforcement.

## Risks / Trade-offs

- Scope leakage via legacy actor/public reads: pinned selection must prove run
  universe matches before returning content or requesting cancellation.
- Output size/type: bounded field reads must be lossless across continuation and
  explicit about serialization/offsets; the existing short text preview is not
  the exact structured return. Review contract before implementing pagination.
- Missing event: preserve real exception identity and parallel siblings; don't
  manufacture success or rely on last-completed node as failed identity.
- Workspace safety: wrong caller defaults could reopen sibling access; tests
  must go through real dispatch, not manually seed a fake HTTP result as ancestry.
- Existing edit field restrictions may encode retired rationale; any removal
  still needs canonical validation, authorship and current create parity proof.

## Migration and proof

### Post-live cancellation display follow-up

The September 8 23:30-23:31 PDT retest on deploy008269579327 confirms the first
four gaps fixed and cancellation physically working, but the stopped code node
still displays running. Strengthening the existing real-child test reproduces
this locally: one failed (running != cancelled), one queued-control pass.
The compiler raises NodeCancelledError without a terminal event; both runner
event translators and the status fold currently know only failed/ran terminals.

Record a distinct cancelled event only when the code sandbox actually reports
cancellation. Preserve original exception, graph-instance identity, completed
siblings and unstarted pending nodes. Both initial and resume translators must
persist this phase; the shared status fold must treat it as terminal. Do not
blanket-relabel every node merely because the run became cancelled, fabricate
failure, mutate old history on read, or change stop/cleanup/authority mechanics.
The diagram consumer must not map a known cancelled state to running/pending.
Check its graph-instance identities while verifying that affected readback.
Use the existing event row/string storage, not a schema migration or new tool.
Confirm shape/basic-safety independently and verify tests + Linux before the
next deployed exact-message retest. Broader resource-policy work stays open.

No stored-data migration. API additions retain current start defaults. Shape and
basic-safety review precedes runtime edits; focused baseline/red/candidate tests,
Linux oracle/CI and exact-head review precede normal guarded merge. Mirror build,
authenticated canary and deployed-SHA gate precede the ordinary app retest.
Revert implementation through reviewed deploy if scope/lifecycle regresses.
Do not archive until the app explicitly confirms five gaps closed. Broader limits
goal remains governed by the parent's goal-completion-contract.md.

## Open implementation questions

Review output boundedness and exact selector contract; determine precisely which
node wrapper owns graph identity and whether queued cancel needs only existing
queue checks. These are engineering questions, not requests for owner mechanics.
